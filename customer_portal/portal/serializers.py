"""DRF serializers backing the Phase 3 admin CRUD ("Manage Data") API.

Field lists mirror portal/admin_forms.py's ModelForms 1:1 - those forms
still back the (soon to be retired) server-rendered create/edit pages for
whichever of these models haven't been cut over to the SPA yet.

Note: DRF's ModelSerializer already derives `required=False` from a model
field's `null=True` (same as `blank=True`), so - unlike admin_forms.py's
TailwindFormMixin, which had to patch this in manually for plain Django
forms - no extra work is needed here to make nullable fields optional.
"""
from django.contrib.auth.models import User
from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from .models import (
    Customer, ProductModel, Motorcycle, FinanceCreditSale,
    FinanceInstallment, FinanceLedger, CustomerPortalAuth,
    Invoice, InvoiceItem,
)
from .permissions import get_profile


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = [
            'id', 'cnic', 'name', 'father_name', 'business_name', 'ntn',
            'phone', 'address', 'type', 'is_deleted',
        ]
        # 'id' here is a plain IntegerField(primary_key=True), not a real
        # AutoField (these managed=False tables are owned by the desktop
        # app), so DRF can't auto-detect it as read-only like it would for
        # a normal PK - it must be listed explicitly or every create() 400s
        # with "This field is required." SQLite still auto-assigns the row
        # id on insert as long as it's left out of the INSERT entirely.
        read_only_fields = ['id', 'is_deleted']


class ProductModelSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductModel
        fields = ['id', 'model_name', 'make', 'engine_capacity', 'pct_code', 'item_code']
        read_only_fields = ['id']


class MotorcycleSerializer(serializers.ModelSerializer):
    product_model_name = serializers.CharField(source='product_model.model_name', read_only=True)

    class Meta:
        model = Motorcycle
        fields = [
            'id', 'product_model', 'product_model_name', 'vin', 'chassis_number',
            'engine_number', 'year', 'color', 'cost_price', 'sale_price',
            'status', 'purchase_date',
        ]
        read_only_fields = ['id']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['product_model'].queryset = ProductModel.objects.order_by('model_name')


class FinanceCreditSaleSerializer(serializers.ModelSerializer):
    class Meta:
        model = FinanceCreditSale
        fields = [
            'id', 'sale_id', 'customer', 'customer_name', 'chassis_no', 'engine_no', 'model',
            'cash_price', 'credit_price', 'down_payment', 'down_payment_method',
            'duration_months', 'duration_days', 'installment_amount',
            'sale_date', 'due_date', 'remaining_balance', 'status',
            'credit_type', 'notes',
        ]
        read_only_fields = ['id']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['customer'].queryset = Customer.objects.filter(is_deleted=False).order_by('name')


class FinanceInstallmentSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    sale_label = serializers.CharField(source='sale.sale_id', read_only=True)

    class Meta:
        model = FinanceInstallment
        fields = [
            'id', 'payment_id', 'sale', 'sale_label', 'customer', 'customer_name', 'paid_amount', 'payment_date',
            'payment_method', 'reference_no', 'notes', 'loan_id', 'installment_no',
            'due_date', 'principal_due', 'interest_due', 'fees_due', 'total_due',
            'late_fee_accrued', 'late_fee_last_calculated_at', 'status',
            'paid_principal', 'paid_interest', 'paid_fees', 'paid_total', 'paid_at',
        ]
        read_only_fields = ['id']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['customer'].queryset = Customer.objects.filter(is_deleted=False).order_by('name')
        self.fields['sale'].queryset = FinanceCreditSale.objects.order_by('-sale_date')


class FinanceLedgerSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    # sale is nullable, so source='sale.sale_id' would raise AttributeError
    # on the None case rather than gracefully resolving - a method field
    # sidesteps that by checking the raw FK column first.
    sale_label = serializers.SerializerMethodField()

    class Meta:
        model = FinanceLedger
        fields = [
            'id', 'ledger_id', 'customer', 'customer_name', 'sale', 'sale_label', 'entry_type', 'description',
            'debit', 'credit', 'balance', 'entry_date',
        ]
        read_only_fields = ['id']

    def get_sale_label(self, obj):
        return obj.sale.sale_id if obj.sale_id else None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['customer'].queryset = Customer.objects.filter(is_deleted=False).order_by('name')
        self.fields['sale'].queryset = FinanceCreditSale.objects.order_by('-sale_date')


class CustomerPortalAuthSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    # Optional on create: the create endpoint auto-derives it from the
    # selected customer (matching the old create-account flow, which only
    # ever asked for a customer). Still editable afterwards. Declared
    # explicitly (rather than auto-generated) so it needs its own
    # UniqueValidator - one isn't added automatically for a manually
    # declared field the way it would be for an auto-generated one.
    phone_number = serializers.CharField(
        required=False, allow_blank=True,
        validators=[UniqueValidator(queryset=CustomerPortalAuth.objects.all())],
    )

    class Meta:
        model = CustomerPortalAuth
        fields = ['id', 'customer', 'customer_name', 'phone_number', 'is_active', 'created_at']
        read_only_fields = ['created_at']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['customer'].queryset = Customer.objects.filter(is_deleted=False).order_by('name')


class InvoiceItemSerializer(serializers.ModelSerializer):
    chassis_number = serializers.CharField(source='motorcycle.chassis_number', read_only=True, default=None)

    class Meta:
        model = InvoiceItem
        fields = [
            'id', 'item_code', 'item_name', 'pct_code', 'quantity', 'tax_rate',
            'sale_value', 'tax_charged', 'further_tax', 'total_amount', 'discount',
            'chassis_number',
        ]


class InvoiceSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source='customer.name', read_only=True, default=None)
    customer_cnic = serializers.CharField(source='customer.cnic', read_only=True, default=None)
    items = InvoiceItemSerializer(many=True, read_only=True)

    class Meta:
        model = Invoice
        fields = [
            'id', 'invoice_number', 'datetime', 'customer_name', 'customer_cnic',
            'total_sale_value', 'total_tax_charged', 'total_further_tax', 'total_amount',
            'discount', 'payment_mode', 'fbr_invoice_number', 'is_fiscalized',
            'sync_status', 'fbr_response_code', 'fbr_response_message',
            'status_updated_at', 'items',
        ]


class StaffUserSerializer(serializers.ModelSerializer):
    """Read-only view of a django.contrib.auth.User for the Staff Management
    (Phase 4) pages. Role/creation/password are handled by dedicated
    api_staff_views actions, not by writing through this serializer."""

    role = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'is_active', 'is_superuser', 'date_joined', 'role']
        read_only_fields = fields

    def get_role(self, obj):
        return get_profile(obj).role
