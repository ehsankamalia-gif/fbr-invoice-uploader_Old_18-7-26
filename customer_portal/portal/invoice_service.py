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

import requests
from django.db import transaction
from tenacity import RetryError

from .db_utils import refresh_pk_after_insert
from .fbr_client import fbr_client, get_active_fbr_settings
from .models import Customer, Invoice, InvoiceItem, Motorcycle, Price

logger = logging.getLogger(__name__)


class InvoiceValidationError(ValueError):
    pass


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


def get_price_for_motorcycle(motorcycle: Motorcycle):
    """Mirrors app/services/price_service.py's get_price_by_model_and_color:
    the active (expiration_date NULL) price row for the bike's model,
    preferring whichever variant's optional_features colour list contains
    the bike's own color, falling back to the first active price."""
    prices = list(Price.objects.filter(product_model_id=motorcycle.product_model_id, expiration_date__isnull=True))
    if not prices:
        return None
    target = ''.join(ch for ch in (motorcycle.color or '') if ch.isalpha()).lower()
    if target:
        for p in prices:
            colors_raw = ''
            if isinstance(p.optional_features, dict):
                colors_raw = p.optional_features.get('colors') or p.optional_features.get('color') or ''
            candidates = [''.join(ch for ch in c.strip() if ch.isalpha()).lower() for c in str(colors_raw).split(',')]
            if target in [c for c in candidates if c]:
                return p
    return prices[0]


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
        raise InvoiceValidationError('Chassis number is required.')

    buyer_cnic = (data.get('buyer_cnic') or '').strip()
    if not buyer_cnic:
        raise InvoiceValidationError('Buyer CNIC is required.')

    settings = get_active_fbr_settings()

    with transaction.atomic():
        motorcycle = Motorcycle.objects.select_for_update().filter(chassis_number=chassis_number).first()
        if not motorcycle:
            raise InvoiceValidationError(f'Motorcycle with chassis {chassis_number} not found in inventory.')
        if motorcycle.status != Motorcycle.IN_STOCK:
            raise InvoiceValidationError(f'Motorcycle {chassis_number} is already {motorcycle.status}.')

        already_fiscalized = InvoiceItem.objects.filter(
            motorcycle_id=motorcycle.id, invoice__is_fiscalized=True,
        ).exists()
        if already_fiscalized:
            raise InvoiceValidationError(f'Chassis {chassis_number} is already fiscalized with FBR.')

        price = get_price_for_motorcycle(motorcycle)

        def _num(key, fallback):
            val = data.get(key)
            return float(val) if val not in (None, '') else fallback

        tax_rate = _num('tax_rate', float(settings.get('tax_rate') or 18.0))
        sale_value = _num('sale_value', float(price.base_price) if price else 0.0)
        tax_charged = _num('tax_charged', float(price.tax_amount) if price else round(sale_value * tax_rate / 100.0, 2))
        further_tax = _num('further_tax', float(price.levy_amount) if price else round(sale_value * 3.0 / 100.0, 2))
        discount = _num('discount', 0.0)

        if sale_value <= 0:
            raise InvoiceValidationError('Sale value must be greater than zero.')

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
                name=(data.get('buyer_name') or '').upper(),
                father_name=(data.get('buyer_father_name') or '').upper(),
                ntn=(data.get('buyer_ntn') or '').upper(),
                phone=data.get('buyer_phone') or '',
                address=(data.get('buyer_address') or '').upper(),
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
            total_quantity=1,
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
            quantity=1,
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
            invoice.fbr_response_message = base_msg
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
            invoice.fbr_response_message = response.get('Response', 'Unknown Error') if response else 'No response'
            invoice.fbr_full_response = response
            logger.warning(f'FBR API Error for {invoice.invoice_number}: {invoice.fbr_response_message}')

    except requests.RequestException as net_err:
        logger.warning(f'Network error syncing {invoice.invoice_number}: {net_err}')
        invoice.sync_status = Invoice.PENDING
        invoice.status_updated_at = _utc_now_literal()
        invoice.fbr_response_message = f'Network Error - Queued for retry: {str(net_err)[:300]}'

    except RetryError as retry_err:
        try:
            original_exception = retry_err.last_attempt.exception()
        except Exception:
            original_exception = None
        if isinstance(original_exception, requests.RequestException):
            invoice.sync_status = Invoice.PENDING
            invoice.status_updated_at = _utc_now_literal()
            invoice.fbr_response_message = f'Network Error (Max Retries) - Queued for retry: {str(original_exception)[:300]}'
        else:
            invoice.sync_status = Invoice.FAILED
            invoice.status_updated_at = _utc_now_literal()
            invoice.fbr_response_message = f'Failed after retries: {original_exception}' if original_exception else 'Failed after retries'

    except Exception as e:
        logger.error(f'Invoice sync failed: {e}')
        invoice.sync_status = Invoice.FAILED
        invoice.status_updated_at = _utc_now_literal()
        invoice.fbr_response_message = str(e)
