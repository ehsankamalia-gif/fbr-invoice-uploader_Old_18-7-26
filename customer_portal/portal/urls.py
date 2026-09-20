from django.contrib.auth.views import LogoutView
from django.urls import path
from django.views.generic import RedirectView
from . import views

urlpatterns = [
    path('credit-customers/', RedirectView.as_view(pattern_name='credit_customers', permanent=False)),
    # Plain (non-JS) logout for the still-live server-rendered admin pages'
    # sidebar form (templates/portal/custom_admin/base.html). The Vue admin
    # area uses the JSON POST /api/v1/auth/staff/logout/ endpoint instead.
    path('custom-admin/logout/', LogoutView.as_view(next_page='/custom-admin/'), name='staff_logout'),
    path('api/customer/<int:customer_id>/', views.get_customer_data, name='get_customer_data'),
    path('admin/credit-customers/', views.credit_customers_view, name='credit_customers'),
    path('custom-admin/export-sales-csv/', views.export_sales_csv, name='export_sales_csv'),
    path('custom-admin/export-payments-csv/', views.export_payments_csv, name='export_payments_csv'),
]
