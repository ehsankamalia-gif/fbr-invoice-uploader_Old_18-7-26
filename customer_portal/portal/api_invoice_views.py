"""Staff-only "Create Invoice" feature: create a sales invoice for one
motorcycle chassis and upload it to FBR (old POS-integration scheme only -
see portal/fbr_client.py), plus a read-only list of what's been submitted
so far. Business logic lives in portal/invoice_service.py."""
import logging

from rest_framework import generics
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from . import invoice_service
from .api_permissions import HasPortalPermission
from .fbr_client import get_active_fbr_settings
from .models import Customer, Invoice, Motorcycle, ProductModel
from .serializers import InvoiceSerializer

logger = logging.getLogger(__name__)


class InvoiceListView(generics.ListAPIView):
    serializer_class = InvoiceSerializer
    permission_classes = [HasPortalPermission('view_invoices')]

    def get_queryset(self):
        qs = Invoice.objects.select_related('customer').prefetch_related('items', 'items__motorcycle').order_by('-id')
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(invoice_number__icontains=search)
        return qs[:200]


@api_view(['GET'])
@permission_classes([HasPortalPermission('create_invoices')])
def invoice_form_options_view(request):
    """Everything the Create Invoice form needs: in-stock motorcycles
    (for the chassis dropdown), the next invoice number preview, and the
    active FBR environment's default item naming/PCT code/tax rate."""
    try:
        settings = get_active_fbr_settings()
    except RuntimeError as e:
        return Response({'detail': str(e)}, status=400)

    motorcycles = Motorcycle.objects.select_related('product_model').filter(status=Motorcycle.IN_STOCK).order_by('chassis_number')
    bikes = [
        {
            'id': m.id,
            'chassis_number': m.chassis_number,
            'engine_number': m.engine_number,
            'model_name': m.product_model.model_name if m.product_model else '',
            'color': m.color,
        }
        for m in motorcycles
    ]

    product_models = [
        {'id': pm.id, 'model_name': pm.model_name}
        for pm in ProductModel.objects.order_by('model_name')
    ]
    known_colors = sorted({
        (c or '').strip().upper()
        for c in Motorcycle.objects.exclude(color__isnull=True).exclude(color='').values_list('color', flat=True).distinct()
    })

    return Response({
        'motorcycles': bikes,
        'product_models': product_models,
        'known_colors': known_colors,
        'next_invoice_number': invoice_service.generate_next_invoice_number(settings.get('usin')),
        'default_tax_rate': float(settings.get('tax_rate') or 18.0),
        'environment': settings.get('env'),
    })


@api_view(['GET'])
@permission_classes([HasPortalPermission('create_invoices')])
def invoice_price_preview_view(request, motorcycle_id):
    """Looks up the active price for a selected motorcycle so the form can
    prefill sale value / tax / further tax before the user submits."""
    try:
        motorcycle = Motorcycle.objects.select_related('product_model').get(id=motorcycle_id)
    except Motorcycle.DoesNotExist:
        return Response({'detail': 'Motorcycle not found.'}, status=404)

    price = invoice_service.get_price_for_motorcycle(motorcycle)
    if not price:
        return Response({'price': None})

    return Response({
        'price': {
            'sale_value': price.base_price,
            'tax_charged': price.tax_amount,
            'further_tax': price.levy_amount,
        }
    })


@api_view(['GET'])
@permission_classes([HasPortalPermission('create_invoices')])
def invoice_price_preview_by_model_view(request, product_model_id):
    """Same as invoice_price_preview_view, but for a chassis that isn't in
    inventory yet - looked up by the manually-selected Model + Color
    instead of an existing motorcycle row."""
    color = request.query_params.get('color') or ''
    if not ProductModel.objects.filter(id=product_model_id).exists():
        return Response({'detail': 'Model not found.'}, status=404)

    price = invoice_service.get_price_for_model_color(product_model_id, color)
    if not price:
        return Response({'price': None})

    return Response({
        'price': {
            'sale_value': price.base_price,
            'tax_charged': price.tax_amount,
            'further_tax': price.levy_amount,
        }
    })


@api_view(['GET'])
@permission_classes([HasPortalPermission('create_invoices')])
def invoice_customer_lookup_view(request):
    """Looks up an existing customer by CNIC so the form can auto-fill
    their name/father name/phone/address - mirrors the desktop app's
    _on_invoice_cnic_changed. Returns {customer: null} rather than 404
    when nothing matches, since "not found yet" is the normal case while
    someone is still typing or this is a brand-new buyer."""
    cnic = (request.query_params.get('cnic') or '').strip()
    if not cnic:
        return Response({'customer': None})

    customer = Customer.objects.filter(cnic=cnic, is_deleted=False).first()
    if not customer:
        return Response({'customer': None})

    return Response({
        'customer': {
            'name': customer.name,
            'father_name': customer.father_name,
            'phone': customer.phone,
            'address': customer.address,
            'ntn': customer.ntn,
            'type': customer.type,
        }
    })


@api_view(['POST'])
@permission_classes([HasPortalPermission('create_invoices')])
def invoice_create_view(request):
    try:
        invoice = invoice_service.create_invoice(request.data)
    except invoice_service.InvoiceValidationError as e:
        if e.field:
            return Response({e.field: [str(e)]}, status=400)
        return Response({'detail': str(e)}, status=400)

    data = InvoiceSerializer(invoice).data
    if invoice.is_fiscalized and invoice.fbr_invoice_number:
        try:
            data['qr_code_base64'] = invoice_service.generate_qr_code_base64(invoice.fbr_invoice_number)
        except Exception:
            logger.warning('QR code generation failed for invoice %s', invoice.invoice_number, exc_info=True)
    return Response(data, status=201)
