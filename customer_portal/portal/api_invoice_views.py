"""Staff-only "Create Invoice" feature: create a sales invoice for one
motorcycle chassis and upload it to FBR (old POS-integration scheme only -
see portal/fbr_client.py), plus a read-only list of what's been submitted
so far. Business logic lives in portal/invoice_service.py."""
from rest_framework import generics
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from . import invoice_service
from .api_permissions import HasPortalPermission
from .fbr_client import get_active_fbr_settings
from .models import Invoice, Motorcycle
from .serializers import InvoiceSerializer


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

    return Response({
        'motorcycles': bikes,
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


@api_view(['POST'])
@permission_classes([HasPortalPermission('create_invoices')])
def invoice_create_view(request):
    try:
        invoice = invoice_service.create_invoice(request.data)
    except invoice_service.InvoiceValidationError as e:
        return Response({'detail': str(e)}, status=400)
    return Response(InvoiceSerializer(invoice).data, status=201)
