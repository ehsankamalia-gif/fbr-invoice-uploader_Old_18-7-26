
from django.contrib import admin
from django.db.models import Count, Q
from django import forms
from django.contrib.auth.hashers import make_password
from .models import (
    Customer, ProductModel, Motorcycle, 
    FinanceCreditSale, FinanceInstallment, FinanceLedger,
    CustomerPortalAuth
)


class HasCreditSalesFilter(admin.SimpleListFilter):
    title = 'Has Credit Sales'
    parameter_name = 'has_credit_sales'
    
    def lookups(self, request, model_admin):
        return (
            ('yes', 'Yes'),
            ('no', 'No'),
        )
    
    def queryset(self, request, queryset):
        if self.value() == 'yes':
            return queryset.annotate(
                credit_sales_count=Count('financecreditsale')
            ).filter(credit_sales_count__gt=0)
        if self.value() == 'no':
            return queryset.annotate(
                credit_sales_count=Count('financecreditsale')
            ).filter(credit_sales_count=0)
        return queryset


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'cnic', 'phone', 'type', 'is_deleted', 'credit_sales_count']
    list_filter = ['type', 'is_deleted', HasCreditSalesFilter]
    search_fields = ['name', 'cnic', 'phone', 'business_name']
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.annotate(
            credit_sales_count=Count('financecreditsale')
        )
        return qs
    
    def credit_sales_count(self, obj):
        return obj.credit_sales_count
    credit_sales_count.admin_order_field = 'credit_sales_count'


class CustomerPortalAuthForm(forms.ModelForm):
    """Custom form for CustomerPortalAuth with auto-population."""

    class Meta:
        model = CustomerPortalAuth
        fields = '__all__'

    class Media:
        js = ('js/customer_portal_auth_admin.js',)


@admin.register(CustomerPortalAuth)
class CustomerPortalAuthAdmin(admin.ModelAdmin):
    form = CustomerPortalAuthForm
    list_display = ['id', 'customer', 'phone_number', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['phone_number', 'customer__name', 'customer__cnic']
    readonly_fields = ['created_at', 'updated_at']

    def save_model(self, request, obj, form, change):
        """Auto-set phone number from customer, and use default password if not set."""
        if obj.customer and not obj.phone_number:
            obj.phone_number = obj.customer.phone or ''
        
        if not obj.password_hash or obj.password_hash == '' or obj.password_hash == '123456789':
            obj.password_hash = make_password('123456789')
        
        super().save_model(request, obj, form, change)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Only show customers with credit sales in the customer dropdown."""
        if db_field.name == "customer":
            kwargs["queryset"] = Customer.objects.filter(
                is_deleted=False,
                id__in=FinanceCreditSale.objects.values_list('customer_id', flat=True).distinct()
            ).order_by('name')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(ProductModel)
class ProductModelAdmin(admin.ModelAdmin):
    list_display = ['id', 'model_name', 'make', 'engine_capacity']
    search_fields = ['model_name', 'make']


@admin.register(Motorcycle)
class MotorcycleAdmin(admin.ModelAdmin):
    list_display = ['id', 'chassis_number', 'engine_number', 'product_model', 'color', 'status']
    list_filter = ['status', 'color']
    search_fields = ['chassis_number', 'engine_number']


@admin.register(FinanceCreditSale)
class FinanceCreditSaleAdmin(admin.ModelAdmin):
    list_display = ['id', 'sale_id', 'customer_name', 'chassis_no', 'status', 'remaining_balance', 'sale_date']
    list_filter = ['status']
    search_fields = ['sale_id', 'customer_name', 'chassis_no']
    date_hierarchy = 'sale_date'


@admin.register(FinanceInstallment)
class FinanceInstallmentAdmin(admin.ModelAdmin):
    list_display = ['id', 'payment_id', 'customer', 'paid_amount', 'status', 'payment_date']
    list_filter = ['status']
    search_fields = ['payment_id', 'reference_no']
    date_hierarchy = 'payment_date'


@admin.register(FinanceLedger)
class FinanceLedgerAdmin(admin.ModelAdmin):
    list_display = ['id', 'ledger_id', 'customer', 'entry_type', 'debit', 'credit', 'balance', 'entry_date']
    list_filter = ['entry_type']
    search_fields = ['ledger_id']
    date_hierarchy = 'entry_date'
