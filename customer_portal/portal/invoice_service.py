"""Invoice creation + FBR upload for the customer portal's staff-only
"Create Invoice" feature. Mirrors app/services/invoice_service.py's
create_invoice/sync_invoice on the desktop side closely enough that both
apps produce identical Invoice/InvoiceItem rows and identical FBR
submission outcomes (SYNCED/FAILED/PENDING semantics, echo detection) -
this is a deliberate port, not an import, so the two apps stay fully
independent (see portal/fbr_client.py's module docstring)."""
import logging
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

try:
    from zoneinfo import ZoneInfo
    _PKT = ZoneInfo('Asia/Karachi')
except Exception:
    _PKT = dt_timezone(timedelta(hours=5))

import base64
import io

import qrcode
import requests
from django.db import transaction
from tenacity import RetryError

from .db_utils import refresh_pk_after_insert
from .fbr_client import fbr_client, get_active_fbr_settings
from .models import Customer, Invoice, InvoiceItem, Motorcycle, Price, ProductModel

logger = logging.getLogger(__name__)


def generate_qr_code_base64(data: str) -> str:
    """Encodes `data` (the FBR-issued fiscal invoice number) into a QR PNG,
    returned as base64 - same approach the desktop app uses for the printed
    invoice's QR code (app/qt_ui/main_window.py generates it locally with
    the qrcode package rather than expecting FBR to return an image)."""
    qr = qrcode.QRCode(version=1, box_size=10, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white')
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return base64.b64encode(buf.getvalue()).decode()


class InvoiceValidationError(ValueError):
    """`field`, when set, is the form field name the error is about, so the
    API can return it in DRF's standard {field: [message]} shape and the
    frontend can show it under that specific input."""

    def __init__(self, message, field=None):
        super().__init__(message)
        self.field = field


def _pk_now_literal():
    """An aware datetime whose wall-clock digits equal the current Asia/
    Karachi time, pre-labeled as UTC. Django (USE_TZ=True, TIME_ZONE=
    Asia/Karachi project-wide) would otherwise treat a naive value as PKT
    and convert it to UTC before storage, shifting the raw bytes written
    to this shared MySQL column by 5 hours relative to how the desktop
    app's SQLAlchemy layer writes naive PKT wall-clock values directly
    with no conversion. Pre-labeling as UTC makes Django's forced
    localtime-to-UTC conversion a no-op, so the literal digits written
    match the desktop app's convention exactly."""
    naive_pkt = datetime.now(_PKT).replace(tzinfo=None)
    return naive_pkt.replace(tzinfo=dt_timezone.utc)


def _utc_now_literal():
    """Same trick, for the one column (status_updated_at) the desktop app
    deliberately stores as real UTC (datetime.utcnow()), not PKT."""
    return datetime.utcnow().replace(tzinfo=dt_timezone.utc)


def _safe_message(text, max_len=255):
    """invoices.fbr_response_message is a varchar(255). FBR's own error
    responses (especially from the Digital Invoicing gateway) can be much
    longer multi-line JSON blobs, and saving one untruncated raises a MySQL
    "Data too long for column" DataError that aborts the whole request
    with a raw 500 - the invoice never gets saved at all, and the portal
    just shows a generic "Failed to create invoice." Truncating here keeps
    the save working; the full response is still preserved separately in
    fbr_full_response for anyone who needs the details."""
    text = str(text) if text is not None else ''
    text = ' '.join(text.split())  # collapse newlines/indentation from raw JSON error bodies
    return text[:max_len]


def generate_next_invoice_number(usin: str) -> str:
    """Format: {USIN}-{0001}, matching the desktop app's
    generate_next_invoice_number exactly (same prefix, same table)."""
    usin = (usin or '').strip() or 'UNKNOWN'
    last = Invoice.objects.filter(invoice_number__startswith=f'{usin}-').order_by('-id').first()
    next_seq = 1
    if last:
        try:
            next_seq = int(last.invoice_number.split('-')[-1]) + 1
        except (ValueError, IndexError):
            next_seq = 1
    return f'{usin}-{next_seq:04d}'


def get_price_for_model_color(product_model_id: int, color: str):
    """Mirrors app/services/price_service.py's get_price_by_model_and_color:
    the active (expiration_date NULL) price row for the model, preferring
    whichever variant's optional_features colour list contains the given
    color, falling back to the first active price."""
    prices = list(Price.objects.filter(product_model_id=product_model_id, expiration_date__isnull=True))
    if not prices:
        return None
    target = ''.join(ch for ch in (color or '') if ch.isalpha()).lower()
    if target:
        for p in prices:
            colors_raw = ''
            if isinstance(p.optional_features, dict):
                colors_raw = p.optional_features.get('colors') or p.optional_features.get('color') or ''
            candidates = [''.join(ch for ch in c.strip() if ch.isalpha()).lower() for c in str(colors_raw).split(',')]
            if target in [c for c in candidates if c]:
                return p
    return prices[0]


def get_price_for_motorcycle(motorcycle: Motorcycle):
    return get_price_for_model_color(motorcycle.product_model_id, motorcycle.color)


def create_invoice(data: dict) -> Invoice:
    """Creates an Invoice + single InvoiceItem for one motorcycle chassis
    and immediately attempts to upload it to FBR, exactly like the desktop
    app's "New Invoice" screen (one bike per invoice). Raises
    InvoiceValidationError for anything the caller/form should have
    prevented (bad chassis, missing buyer info, etc). FBR-side failures do
    NOT raise - the Invoice is still saved locally with sync_status FAILED
    or PENDING, same as the desktop app, so it shows up for follow-up."""
    chassis_number = (data.get('chassis_number') or '').strip().upper()
    if not chassis_number:
        raise InvoiceValidationError('Chassis number is required.', field='chassis_number')

    buyer_cnic = (data.get('buyer_cnic') or '').strip()
    if not buyer_cnic:
        raise InvoiceValidationError('Buyer CNIC is required.', field='buyer_cnic')
    cnic_digits = ''.join(ch for ch in buyer_cnic if ch.isdigit())
    if len(cnic_digits) != 13:
        raise InvoiceValidationError('Buyer CNIC must be exactly 13 digits.', field='buyer_cnic')

    # Matches the desktop app's own required-field list for this form
    # (_check_invoice_form_completeness): CNIC, name, father name, phone,
    # address are all mandatory - only NTN is optional.
    buyer_name = (data.get('buyer_name') or '').strip()
    if not buyer_name:
        raise InvoiceValidationError('Buyer name is required.', field='buyer_name')
    if not all(ch.isalpha() or ch.isspace() for ch in buyer_name):
        raise InvoiceValidationError('Buyer name must contain letters only.', field='buyer_name')

    buyer_father_name = (data.get('buyer_father_name') or '').strip()
    if not buyer_father_name:
        raise InvoiceValidationError('Father name is required.', field='buyer_father_name')
    if not all(ch.isalpha() or ch.isspace() for ch in buyer_father_name):
        raise InvoiceValidationError('Father name must contain letters only.', field='buyer_father_name')

    buyer_phone = (data.get('buyer_phone') or '').strip()
    if not buyer_phone:
        raise InvoiceValidationError('Buyer phone number is required.', field='buyer_phone')
    if len(buyer_phone) != 11 or not buyer_phone.isdigit():
        raise InvoiceValidationError('Buyer phone number must be exactly 11 digits.', field='buyer_phone')

    buyer_address = (data.get('buyer_address') or '').strip()
    if not buyer_address:
        raise InvoiceValidationError('Buyer address is required.', field='buyer_address')

    settings = get_active_fbr_settings()

    with transaction.atomic():
        motorcycle = Motorcycle.objects.select_for_update().filter(chassis_number=chassis_number).first()
        if motorcycle:
            if motorcycle.status != Motorcycle.IN_STOCK:
                raise InvoiceValidationError(f'Motorcycle {chassis_number} is already {motorcycle.status}.', field='chassis_number')

            already_fiscalized = InvoiceItem.objects.filter(
                motorcycle_id=motorcycle.id, invoice__is_fiscalized=True,
            ).exists()
            if already_fiscalized:
                raise InvoiceValidationError(f'Chassis {chassis_number} is already fiscalized with FBR.', field='chassis_number')

            price = get_price_for_motorcycle(motorcycle)
        else:
            # Chassis not in inventory - mirrors the desktop app's
            # invoice_service.create_invoice fallback: create the
            # Motorcycle record on the fly, already SOLD, as long as a
            # model and color were given.
            product_model_id = data.get('product_model_id')
            color = (data.get('color') or '').strip()
            if not product_model_id:
                raise InvoiceValidationError(
                    f'Chassis {chassis_number} was not found in inventory. Select a Model.', field='product_model_id'
                )
            if not color:
                raise InvoiceValidationError(
                    f'Chassis {chassis_number} was not found in inventory. Select a Color.', field='color'
                )
            product_model = ProductModel.objects.filter(id=product_model_id).first()
            if not product_model:
                raise InvoiceValidationError('Selected model was not found.', field='product_model_id')

            engine_number = (data.get('engine_number') or '').strip().upper()
            if not engine_number:
                engine_number = f'UNKNOWN-{chassis_number}'

            motorcycle = Motorcycle(
                chassis_number=chassis_number,
                engine_number=engine_number,
                product_model=product_model,
                year=datetime.now().year,
                color=color.upper(),
                cost_price=0.0,
                sale_price=0.0,
                status=Motorcycle.SOLD,
                purchase_date=_pk_now_literal(),
            )
            motorcycle.save()
            refresh_pk_after_insert(motorcycle)

            price = get_price_for_model_color(product_model.id, color)

        def _num(key, fallback):
            val = data.get(key)
            return float(val) if val not in (None, '') else fallback

        quantity = _num('quantity', 1.0)
        if quantity <= 0:
            raise InvoiceValidationError('Quantity must be greater than zero.', field='quantity')

        tax_rate = _num('tax_rate', float(settings.get('tax_rate') or 18.0))
        unit_sale_value = _num('sale_value', float(price.base_price) if price else 0.0)
        unit_tax_charged = _num('tax_charged', float(price.tax_amount) if price else round(unit_sale_value * tax_rate / 100.0, 2))
        unit_further_tax = _num('further_tax', float(price.levy_amount) if price else round(unit_sale_value * 3.0 / 100.0, 2))
        discount = _num('discount', 0.0)

        if unit_sale_value <= 0:
            raise InvoiceValidationError('Sale value must be greater than zero.', field='sale_value')

        # sale_value/tax_charged/further_tax are per-unit; the invoice/item
        # line reports the quantity-scaled total (standard invoicing
        # convention: line total = unit price x quantity), with Quantity
        # reported separately in the FBR payload.
        sale_value = round(unit_sale_value * quantity, 2)
        tax_charged = round(unit_tax_charged * quantity, 2)
        further_tax = round(unit_further_tax * quantity, 2)
        total_amount = sale_value + tax_charged + further_tax

        buyer_type = data.get('buyer_type') or Customer.INDIVIDUAL
        if buyer_type not in (Customer.INDIVIDUAL, Customer.DEALER):
            buyer_type = Customer.INDIVIDUAL

        customer = Customer.objects.filter(cnic=buyer_cnic).first()
        if customer:
            # Existing customer: don't overwrite permanent details (name,
            # father_name, phone, address) from the invoice form - only
            # NTN/type/is_deleted, matching desktop invoice_service.py.
            if data.get('buyer_ntn'):
                customer.ntn = (data.get('buyer_ntn') or '').upper()
            if buyer_type == Customer.DEALER:
                customer.type = Customer.DEALER
            customer.is_deleted = False
            customer.save()
        else:
            customer = Customer(
                cnic=buyer_cnic,
                name=buyer_name.upper(),
                father_name=buyer_father_name.upper(),
                ntn=(data.get('buyer_ntn') or '').upper(),
                phone=buyer_phone,
                address=buyer_address.upper(),
                type=buyer_type,
                is_deleted=False,
                created_at=_pk_now_literal(),
            )
            customer.save()
            refresh_pk_after_insert(customer)

        usin_prefix = (settings.get('usin') or '').strip()
        invoice_number = generate_next_invoice_number(usin_prefix)

        item_name_base = settings.get('item_name') or 'Motorcycle'
        item_code_base = settings.get('item_code') or 'MOTO'
        pct_code = settings.get('pct_code') or '8711.2010'
        model_name = motorcycle.product_model.model_name
        color = motorcycle.color or ''
        final_item_name = f'{item_name_base} {model_name} {color}'.strip()
        final_item_code = f'{item_code_base}-{model_name}-{color}'.strip('-')

        invoice = Invoice(
            invoice_number=invoice_number,
            pos_id=settings.get('pos_id') or '',
            usin=invoice_number,
            datetime=_pk_now_literal(),
            customer=customer,
            total_sale_value=sale_value,
            total_tax_charged=tax_charged,
            total_further_tax=further_tax,
            total_quantity=quantity,
            total_amount=total_amount,
            discount=discount,
            payment_mode=data.get('payment_mode') or 'Cash',
            is_fiscalized=False,
            sync_status=Invoice.PENDING,
            fbr_response_message='Created via customer portal. Waiting for upload.',
            status_updated_at=_utc_now_literal(),
        )
        invoice.save()
        refresh_pk_after_insert(invoice)

        motorcycle.status = Motorcycle.SOLD
        motorcycle.save(update_fields=['status'])

        item = InvoiceItem(
            invoice=invoice,
            motorcycle=motorcycle,
            item_code=final_item_code,
            item_name=final_item_name,
            pct_code=pct_code,
            quantity=quantity,
            tax_rate=tax_rate,
            sale_value=sale_value,
            tax_charged=tax_charged,
            further_tax=further_tax,
            total_amount=total_amount,
            discount=discount,
        )
        item.save()
        refresh_pk_after_insert(item)

        _sync_invoice(invoice, item, settings)
        invoice.save()

    return invoice


def _sync_invoice(invoice: Invoice, item: InvoiceItem, settings: dict) -> None:
    """Uploads to FBR and updates invoice.sync_status/fbr_* fields in
    place (caller is responsible for saving). Never raises - all FBR/
    network failures are captured onto the invoice itself, matching the
    desktop app's sync_invoice."""
    invoice_data = {
        'invoice_number': invoice.invoice_number,
        'datetime': invoice.datetime,
        'buyer_name': invoice.customer.name if invoice.customer else '',
        'buyer_ntn': invoice.customer.ntn if invoice.customer else '',
        'buyer_cnic': invoice.customer.cnic if invoice.customer else '',
        'buyer_phone': invoice.customer.phone if invoice.customer else '',
        'total_sale_value': invoice.total_sale_value,
        'total_tax_charged': invoice.total_tax_charged,
        'total_further_tax': invoice.total_further_tax,
        'total_quantity': invoice.total_quantity,
        'total_amount': invoice.total_amount,
        'payment_mode': invoice.payment_mode,
        'ref_usin': None,
        'items': [{
            'item_code': item.item_code,
            'item_name': item.item_name,
            'quantity': item.quantity,
            'tax_rate': item.tax_rate,
            'sale_value': item.sale_value,
            'tax_charged': item.tax_charged,
            'further_tax': item.further_tax,
            'total_amount': item.total_amount,
            'pct_code': item.pct_code,
            'discount': item.discount,
            'invoice_type': None,
            'ref_usin': None,
        }],
    }

    try:
        try:
            response = fbr_client.post_invoice(invoice_data, settings)
            logger.info(f'FBR API Raw Response for {invoice.invoice_number}: {response}')
        except Exception as sync_err:
            logger.error(f'FBR API call failed for {invoice.invoice_number}: {sync_err}', exc_info=True)
            raise

        response_code = str(response.get('Code')) if response and response.get('Code') else None
        is_success = response_code == '100'

        returned_fbr_id = response.get('InvoiceNumber') or response.get('FBRInvoiceNo') or None
        returned_usin = response.get('USIN') or response.get('FBRUSIN') or None
        verification_url = (
            response.get('VerificationURL') or response.get('VerificationUrl') or response.get('QrCodeUrl') or None
        )
        qr_code = response.get('QrCode') or response.get('QRCode') or response.get('QRCodeImage') or None
        iris_validated = response.get('IrisValidated') if response else None
        is_verified = response.get('IsVerified') if response else None
        if is_verified is None and iris_validated is None:
            candidate = returned_usin or returned_fbr_id
            if candidate and candidate != invoice.invoice_number and len(candidate) >= 10:
                is_verified = True

        fbr_has_verification_artifacts = bool(returned_usin or verification_url or iris_validated or is_verified or qr_code)
        is_echo = (
            not fbr_has_verification_artifacts
            and returned_fbr_id is not None
            and returned_fbr_id == invoice.invoice_number
        )

        if is_success and returned_fbr_id and not is_echo:
            invoice.fbr_invoice_number = returned_fbr_id
            invoice.usin = returned_usin or returned_fbr_id or invoice.usin
            invoice.is_fiscalized = True
            invoice.sync_status = Invoice.SYNCED
            invoice.status_updated_at = _utc_now_literal()
            invoice.fbr_response_code = response_code
            response_text = response.get('Response')
            if isinstance(is_verified, bool) and is_verified:
                base_msg = 'Verified & Fiscalized'
            elif iris_validated:
                base_msg = 'Fiscalized (IRIS Validated)'
            else:
                base_msg = str(response_text) if response_text else 'Success'
            invoice.fbr_response_message = _safe_message(base_msg)
            invoice.fbr_full_response = response
            logger.info(f'FBR SUCCESS: Invoice {invoice.invoice_number} fiscalized as {returned_fbr_id}')

        elif is_echo:
            logger.error(f'FBR ECHO FAILURE: FBR returned echoed Invoice Number for {invoice.invoice_number}')
            invoice.sync_status = Invoice.FAILED
            invoice.status_updated_at = _utc_now_literal()
            invoice.fbr_response_message = 'FBR returned echoed Invoice Number (FBR Glitch)'
            invoice.fbr_full_response = response

        else:
            invoice.sync_status = Invoice.FAILED
            invoice.status_updated_at = _utc_now_literal()
            invoice.fbr_response_message = _safe_message(response.get('Response', 'Unknown Error') if response else 'No response')
            invoice.fbr_full_response = response
            logger.warning(f'FBR API Error for {invoice.invoice_number}: {invoice.fbr_response_message}')

    except requests.RequestException as net_err:
        logger.warning(f'Network error syncing {invoice.invoice_number}: {net_err}')
        invoice.sync_status = Invoice.PENDING
        invoice.status_updated_at = _utc_now_literal()
        invoice.fbr_response_message = _safe_message(f'Network Error - Queued for retry: {net_err}')

    except RetryError as retry_err:
        try:
            original_exception = retry_err.last_attempt.exception()
        except Exception:
            original_exception = None
        if isinstance(original_exception, requests.RequestException):
            invoice.sync_status = Invoice.PENDING
            invoice.status_updated_at = _utc_now_literal()
            invoice.fbr_response_message = _safe_message(f'Network Error (Max Retries) - Queued for retry: {original_exception}')
        else:
            invoice.sync_status = Invoice.FAILED
            invoice.status_updated_at = _utc_now_literal()
            invoice.fbr_response_message = _safe_message(f'Failed after retries: {original_exception}' if original_exception else 'Failed after retries')

    except Exception as e:
        logger.error(f'Invoice sync failed: {e}')
        invoice.sync_status = Invoice.FAILED
        invoice.status_updated_at = _utc_now_literal()
        invoice.fbr_response_message = _safe_message(e)
