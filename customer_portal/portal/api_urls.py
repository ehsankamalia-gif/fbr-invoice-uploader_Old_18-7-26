from django.urls import path

from . import api_views, api_crud_views, api_company_views, api_fbr_config_views, api_invoice_views, api_staff_views

urlpatterns = [
    path('auth/session/', api_views.session_view, name='api_session'),
    path('auth/customer/login/', api_views.customer_login_view, name='api_customer_login'),
    path('auth/customer/logout/', api_views.customer_logout_view, name='api_customer_logout'),
    path('auth/staff/login/', api_views.staff_login_view, name='api_staff_login'),
    path('auth/staff/logout/', api_views.staff_logout_view, name='api_staff_logout'),

    path('customer/dashboard/', api_views.customer_dashboard_view, name='api_customer_dashboard'),
    path('customer/loans/<str:loan_type>/<int:loan_id>/', api_views.customer_loan_detail_view, name='api_customer_loan_detail'),
    path('customer/payments/', api_views.customer_payments_view, name='api_customer_payments'),
    path('customer/profile/', api_views.customer_profile_view, name='api_customer_profile'),
    path('customer/running-ledger/', api_views.customer_running_ledger_view, name='api_customer_running_ledger'),

    path('admin/dashboard/', api_views.admin_dashboard_view, name='api_admin_dashboard'),
    path('admin/customers/', api_views.admin_customers_view, name='api_admin_customers'),
    path('admin/customer-summary/', api_views.admin_customer_summary_view, name='api_admin_customer_summary'),
    path('admin/customer-summary/<int:customer_id>/', api_views.admin_customer_detail_view, name='api_admin_customer_detail'),
    path('admin/customer-summary/<int:customer_id>/ledger/', api_views.admin_customer_ledger_view, name='api_admin_customer_ledger'),
    path('admin/sales/', api_views.admin_sales_view, name='api_admin_sales'),
    path('admin/payments/', api_views.admin_payments_view, name='api_admin_payments'),
    path('admin/inventory/', api_views.admin_inventory_view, name='api_admin_inventory'),
    path('admin/transactions/', api_views.admin_transactions_view, name='api_admin_transactions'),
    path('admin/ledgers/old-credit/', api_views.admin_old_credit_ledger_view, name='api_admin_old_credit_ledger'),
    path('admin/ledgers/finance-credit/', api_views.admin_finance_credit_ledger_view, name='api_admin_finance_credit_ledger'),
    path('admin/ledgers/combined/', api_views.admin_combined_ledger_view, name='api_admin_combined_ledger'),
    path('admin/spare-ledger/transactions/', api_views.admin_spare_ledger_transactions_view, name='api_admin_spare_ledger_transactions'),
    path('admin/spare-ledger/monthly-report/', api_views.admin_spare_ledger_monthly_report_view, name='api_admin_spare_ledger_monthly_report'),
    path('admin/spare-ledger/monthly-summary/', api_views.admin_spare_ledger_monthly_summary_view, name='api_admin_spare_ledger_monthly_summary'),

    # --- Phase 3: admin CRUD ("Manage Data") ---
    path('admin/options/customers/', api_crud_views.customer_options_view, name='api_customer_options'),
    path('admin/options/finance-sales/', api_crud_views.finance_sale_options_view, name='api_finance_sale_options'),

    path('admin/manage/customers/', api_crud_views.CustomerListCreateView.as_view(), name='api_manage_customers'),
    path('admin/manage/customers/<int:pk>/', api_crud_views.CustomerDetailView.as_view(), name='api_manage_customer_detail'),
    path('admin/manage/customers/<int:pk>/toggle-deleted/', api_crud_views.customer_toggle_deleted_view, name='api_manage_customer_toggle_deleted'),

    path('admin/manage/product-models/', api_crud_views.ProductModelListCreateView.as_view(), name='api_manage_product_models'),
    path('admin/manage/product-models/<int:pk>/', api_crud_views.ProductModelDetailView.as_view(), name='api_manage_product_model_detail'),

    path('admin/manage/motorcycles/', api_crud_views.MotorcycleCreateView.as_view(), name='api_manage_motorcycle_create'),
    path('admin/manage/motorcycles/<int:pk>/', api_crud_views.MotorcycleDetailView.as_view(), name='api_manage_motorcycle_detail'),

    path('admin/manage/finance-sales/', api_crud_views.FinanceCreditSaleCreateView.as_view(), name='api_manage_finance_sale_create'),
    path('admin/manage/finance-sales/<int:pk>/', api_crud_views.FinanceCreditSaleDetailView.as_view(), name='api_manage_finance_sale_detail'),

    path('admin/manage/finance-installments/', api_crud_views.FinanceInstallmentListCreateView.as_view(), name='api_manage_finance_installments'),
    path('admin/manage/finance-installments/<int:pk>/', api_crud_views.FinanceInstallmentDetailView.as_view(), name='api_manage_finance_installment_detail'),

    path('admin/manage/finance-ledger/', api_crud_views.FinanceLedgerListCreateView.as_view(), name='api_manage_finance_ledger'),
    path('admin/manage/finance-ledger/<int:pk>/', api_crud_views.FinanceLedgerDetailView.as_view(), name='api_manage_finance_ledger_detail'),

    path('admin/manage/portal-accounts/', api_crud_views.PortalAuthListCreateView.as_view(), name='api_manage_portal_accounts'),
    path('admin/manage/portal-accounts/eligible-customers/', api_crud_views.portal_auth_eligible_customers_view, name='api_manage_portal_accounts_eligible'),
    path('admin/manage/portal-accounts/<int:pk>/', api_crud_views.PortalAuthDetailView.as_view(), name='api_manage_portal_account_detail'),
    path('admin/manage/portal-accounts/<int:pk>/reset-password/', api_crud_views.portal_auth_reset_password_view, name='api_manage_portal_account_reset_password'),
    path('admin/manage/portal-accounts/<int:pk>/toggle-active/', api_crud_views.portal_auth_toggle_active_view, name='api_manage_portal_account_toggle_active'),

    # --- Invoices (create + upload to FBR) ---
    path('admin/invoices/', api_invoice_views.InvoiceListView.as_view(), name='api_invoice_list'),
    path('admin/invoices/create/', api_invoice_views.invoice_create_view, name='api_invoice_create'),
    path('admin/invoices/options/', api_invoice_views.invoice_form_options_view, name='api_invoice_options'),
    path('admin/invoices/price-preview/<int:motorcycle_id>/', api_invoice_views.invoice_price_preview_view, name='api_invoice_price_preview'),
    path('admin/invoices/price-preview-by-model/<int:product_model_id>/', api_invoice_views.invoice_price_preview_by_model_view, name='api_invoice_price_preview_by_model'),
    path('admin/invoices/customer-lookup/', api_invoice_views.invoice_customer_lookup_view, name='api_invoice_customer_lookup'),

    # --- FBR Configuration (shared with the desktop app's Settings screen) ---
    path('admin/fbr-config/', api_fbr_config_views.fbr_config_list_view, name='api_fbr_config_list'),
    path('admin/fbr-config/<str:environment>/', api_fbr_config_views.fbr_config_update_view, name='api_fbr_config_update'),
    path('admin/fbr-config/<str:environment>/activate/', api_fbr_config_views.fbr_config_activate_view, name='api_fbr_config_activate'),

    # --- Company profiles (multi-company support) ---
    path('admin/companies/', api_company_views.company_list_view, name='api_company_list'),
    path('admin/companies/<int:pk>/', api_company_views.company_update_view, name='api_company_update'),
    path('admin/companies/<int:pk>/activate/', api_company_views.company_activate_view, name='api_company_activate'),

    # --- Phase 4: Staff Management ---
    path('admin/staff/', api_staff_views.StaffListView.as_view(), name='api_staff_list'),
    path('admin/staff/create/', api_staff_views.staff_create_view, name='api_staff_create'),
    path('admin/staff/<int:user_id>/permissions/', api_staff_views.StaffPermissionsView.as_view(), name='api_staff_permissions'),
    path('admin/staff/<int:user_id>/toggle-active/', api_staff_views.staff_toggle_active_view, name='api_staff_toggle_active'),
    path('admin/staff/<int:user_id>/reset-password/', api_staff_views.staff_reset_password_view, name='api_staff_reset_password'),
]
