"""Phase 3 JSON API: admin CRUD ("Manage Data") for the models that used to
be raw-Django-admin-only, then got a server-rendered custom-admin CRUD page
earlier this project, and are now being cut over to the Vue 3 SPA.

Read endpoints for Motorcycle and FinanceCreditSale already exist in
api_views.py (Inventory / Sales, ported in Phase 2) - only create/edit/delete
are added here for those two, matching how their list pages already work."""

from django.contrib.auth.hashers import make_password
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .api_permissions import HasPortalPermission, IsStaffMember
from .db_utils import refresh_pk_after_insert as _refresh_pk_after_insert
from .models import (
    Customer, ProductModel, Motorcycle, FinanceCreditSale,
    FinanceInstallment, FinanceLedger, CustomerPortalAuth,
)
from .serializers import (
    CustomerSerializer, ProductModelSerializer, MotorcycleSerializer,
    FinanceCreditSaleSerializer, FinanceInstallmentSerializer, FinanceLedgerSerializer,
    CustomerPortalAuthSerializer,
)

FK_DELETE_WARNING = (
    'This record may still be referenced by other ledger/sale records. '
    'Deleting it will not update those related records automatically.'
)


# --- Customers ---------------------------------------------------------

class CustomerListCreateView(generics.ListCreateAPIView):
    serializer_class = CustomerSerializer
    permission_classes = [HasPortalPermission('manage_customers')]

    def get_queryset(self):
        qs = Customer.objects.all().order_by('-id')
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(cnic__icontains=search) | Q(phone__icontains=search))
        return qs

    def perform_create(self, serializer):
        _refresh_pk_after_insert(serializer.save(is_deleted=False))


class CustomerDetailView(generics.RetrieveUpdateAPIView):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    permission_classes = [HasPortalPermission('manage_customers')]


@api_view(['POST'])
@permission_classes([HasPortalPermission('manage_customers')])
def customer_toggle_deleted_view(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    customer.is_deleted = not customer.is_deleted
    customer.save(update_fields=['is_deleted'])
    return Response(CustomerSerializer(customer).data)


# --- Product Models -----------------------------------------------------

class ProductModelListCreateView(generics.ListCreateAPIView):
    queryset = ProductModel.objects.all().order_by('model_name')
    serializer_class = ProductModelSerializer
    permission_classes = [HasPortalPermission('manage_product_models')]

    def perform_create(self, serializer):
        _refresh_pk_after_insert(serializer.save())


class ProductModelDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = ProductModel.objects.all()
    serializer_class = ProductModelSerializer
    permission_classes = [HasPortalPermission('manage_product_models')]


# --- Motorcycles (list is the existing Inventory endpoint) --------------

class MotorcycleCreateView(generics.CreateAPIView):
    serializer_class = MotorcycleSerializer
    permission_classes = [HasPortalPermission('manage_inventory')]

    def perform_create(self, serializer):
        _refresh_pk_after_insert(serializer.save())


class MotorcycleDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Motorcycle.objects.select_related('product_model')
    serializer_class = MotorcycleSerializer
    permission_classes = [HasPortalPermission('manage_inventory')]


# --- Finance Credit Sales (list is the existing Sales endpoint) ---------

class FinanceCreditSaleCreateView(generics.CreateAPIView):
    serializer_class = FinanceCreditSaleSerializer
    permission_classes = [HasPortalPermission('manage_finance_sales')]

    def perform_create(self, serializer):
        _refresh_pk_after_insert(serializer.save())


class FinanceCreditSaleDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = FinanceCreditSale.objects.select_related('customer')
    serializer_class = FinanceCreditSaleSerializer
    permission_classes = [HasPortalPermission('manage_finance_sales')]


# --- Finance Installments ------------------------------------------------

class FinanceInstallmentListCreateView(generics.ListCreateAPIView):
    queryset = FinanceInstallment.objects.select_related('customer', 'sale').order_by('-payment_date')
    serializer_class = FinanceInstallmentSerializer
    permission_classes = [HasPortalPermission('manage_finance_installments')]

    def perform_create(self, serializer):
        _refresh_pk_after_insert(serializer.save())


class FinanceInstallmentDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = FinanceInstallment.objects.select_related('customer', 'sale')
    serializer_class = FinanceInstallmentSerializer
    permission_classes = [HasPortalPermission('manage_finance_installments')]


# --- Finance Ledger -------------------------------------------------------

class FinanceLedgerListCreateView(generics.ListCreateAPIView):
    queryset = FinanceLedger.objects.select_related('customer', 'sale').order_by('-entry_date')
    serializer_class = FinanceLedgerSerializer
    permission_classes = [HasPortalPermission('manage_finance_ledger')]

    def perform_create(self, serializer):
        _refresh_pk_after_insert(serializer.save())


class FinanceLedgerDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = FinanceLedger.objects.select_related('customer', 'sale')
    serializer_class = FinanceLedgerSerializer
    permission_classes = [HasPortalPermission('manage_finance_ledger')]


# --- Customer Portal Auth accounts ---------------------------------------

class PortalAuthListCreateView(generics.ListCreateAPIView):
    queryset = CustomerPortalAuth.objects.select_related('customer').order_by('-created_at')
    serializer_class = CustomerPortalAuthSerializer

    def get_permissions(self):
        # Viewing the list only needs view_portal_accounts; creating a new
        # account needs the stronger manage_portal_accounts, matching the
        # split already used by the (still server-rendered) list/create pages.
        code = 'view_portal_accounts' if self.request.method == 'GET' else 'manage_portal_accounts'
        return [HasPortalPermission(code)()]

    def perform_create(self, serializer):
        customer = serializer.validated_data.get('customer')
        phone_number = serializer.validated_data.get('phone_number') or (customer.phone if customer else '') or ''
        serializer.save(phone_number=phone_number, password_hash=make_password('123456789'), is_active=True)


class PortalAuthDetailView(generics.RetrieveUpdateAPIView):
    queryset = CustomerPortalAuth.objects.select_related('customer')
    serializer_class = CustomerPortalAuthSerializer
    permission_classes = [HasPortalPermission('manage_portal_accounts')]


@api_view(['GET'])
@permission_classes([HasPortalPermission('manage_portal_accounts')])
def portal_auth_eligible_customers_view(request):
    """Credit customers who don't already have a portal account - for the
    "Create Account" dropdown."""
    customers = Customer.objects.filter(
        is_deleted=False,
        id__in=FinanceCreditSale.objects.values_list('customer_id', flat=True).distinct(),
    ).exclude(
        id__in=CustomerPortalAuth.objects.values_list('customer_id', flat=True),
    ).order_by('name')
    return Response([{'id': c.id, 'name': c.name, 'phone': c.phone} for c in customers])


@api_view(['POST'])
@permission_classes([HasPortalPermission('manage_portal_accounts')])
def portal_auth_reset_password_view(request, pk):
    auth = get_object_or_404(CustomerPortalAuth, pk=pk)
    auth.password_hash = make_password('123456789')
    auth.save(update_fields=['password_hash'])
    return Response({'ok': True})


@api_view(['GET'])
@permission_classes([IsStaffMember])
def customer_options_view(request):
    """Lightweight id/name list for customer dropdowns across the various
    manage_* create/edit forms. Any staff member can call this - it's just
    a reference lookup, no more sensitive than what each already-gated
    form page needs to render its own customer <select>."""
    customers = Customer.objects.filter(is_deleted=False).order_by('name')
    return Response([{'id': c.id, 'name': c.name} for c in customers])


@api_view(['GET'])
@permission_classes([IsStaffMember])
def finance_sale_options_view(request):
    """Lightweight id/label list for the "sale" dropdown on the Finance
    Installment and Finance Ledger forms."""
    sales = FinanceCreditSale.objects.order_by('-sale_date')
    return Response([{'id': s.id, 'sale_id': s.sale_id, 'customer_name': s.customer_name} for s in sales])


@api_view(['POST'])
@permission_classes([HasPortalPermission('manage_portal_accounts')])
def portal_auth_toggle_active_view(request, pk):
    auth = get_object_or_404(CustomerPortalAuth, pk=pk)
    auth.is_active = not auth.is_active
    auth.save(update_fields=['is_active'])
    return Response(CustomerPortalAuthSerializer(auth).data)
