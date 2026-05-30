
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from portal.views import (
    credit_customers_view,
    custom_admin_dashboard_view,
    custom_admin_customers_view,
    custom_admin_sales_view,
    custom_admin_payments_view,
    custom_admin_inventory_view,
    custom_admin_transactions_view,
    custom_admin_customer_summary_view,
    custom_admin_customer_detail_view,
    custom_admin_customer_ledger_view,
    custom_admin_old_credit_ledger_view,
    custom_admin_finance_credit_ledger_view,
    custom_admin_combined_credit_ledger_view,
    export_sales_csv,
    export_payments_csv,
    get_customer_data,
    custom_admin_portal_auths_view,
    custom_admin_create_portal_auth_view,
    custom_admin_reset_portal_password_view,
    custom_admin_toggle_portal_active_view
)

urlpatterns = [
    path('api/customer/<int:customer_id>/', get_customer_data, name='get_customer_data'),
    path('', custom_admin_dashboard_view, name='custom_admin_dashboard'),
    path('customers/', custom_admin_customers_view, name='custom_admin_customers'),
    path('customer-summary/', custom_admin_customer_summary_view, name='custom_admin_customer_summary'),
    path('customer/<int:customer_id>/', custom_admin_customer_detail_view, name='custom_admin_customer_detail'),
    path('customer/<int:customer_id>/ledger/', custom_admin_customer_ledger_view, name='custom_admin_customer_ledger'),
    path('ledger/old/', custom_admin_old_credit_ledger_view, name='custom_admin_old_credit_ledger'),
    path('ledger/finance/', custom_admin_finance_credit_ledger_view, name='custom_admin_finance_credit_ledger'),
    path('ledger/combined/', custom_admin_combined_credit_ledger_view, name='custom_admin_combined_credit_ledger'),
    path('sales/', custom_admin_sales_view, name='custom_admin_sales'),
    path('sales/export/', export_sales_csv, name='export_sales_csv'),
    path('payments/', custom_admin_payments_view, name='custom_admin_payments'),
    path('payments/export/', export_payments_csv, name='export_payments_csv'),
    path('inventory/', custom_admin_inventory_view, name='custom_admin_inventory'),
    path('transactions/', custom_admin_transactions_view, name='custom_admin_transactions'),
    path('portal-accounts/', custom_admin_portal_auths_view, name='custom_admin_portal_auths'),
    path('portal-accounts/create/', custom_admin_create_portal_auth_view, name='custom_admin_create_portal_auth'),
    path('portal-accounts/<int:auth_id>/reset-password/', custom_admin_reset_portal_password_view, name='custom_admin_reset_portal_password'),
    path('portal-accounts/<int:auth_id>/toggle-active/', custom_admin_toggle_portal_active_view, name='custom_admin_toggle_portal_active'),
    path('credit-customers/', credit_customers_view, name='admin_credit_customers'),
    path('admin/credit-customers/', credit_customers_view, name='admin_credit_customers_old'),
    path('admin/', admin.site.urls),
    path('portal/', include('portal.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
