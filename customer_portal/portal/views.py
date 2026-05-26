
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.hashers import make_password
from django.db.models import Sum, Count, Q, Avg, F
from django.utils import timezone
from datetime import timedelta
from django.http import HttpResponse, JsonResponse
import csv
from .forms import LoginForm
from .models import (
    Customer, FinanceCreditSale, FinanceInstallment, FinanceLedger,
    ProductModel, Motorcycle, CustomerPortalAuth
)


@staff_member_required
def get_customer_data(request, customer_id):
    """API endpoint to get customer data for admin form auto-population."""
    customer = get_object_or_404(Customer, id=customer_id)
    return JsonResponse({
        'phone': customer.phone,
        'cnic': customer.cnic,
    })


def customer_login_required(view_func):
    def wrapper(request, *args, **kwargs):
        if 'customer_id' not in request.session:
            return redirect('login')
        return view_func(request, *args, **kwargs)
    return wrapper


def login_view(request):
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            customer = form.cleaned_data['customer']
            request.session['customer_id'] = customer.id
            request.session['customer_name'] = customer.name
            request.session['customer_type'] = customer.type
            messages.success(request, f'Welcome back, {customer.name}!')
            return redirect('dashboard')
    else:
        form = LoginForm()
    
    return render(request, 'portal/login.html', {'form': form})


def logout_view(request):
    request.session.flush()
    messages.info(request, 'You have been logged out successfully.')
    return redirect('login')


@customer_login_required
def dashboard_view(request):
    customer_id = request.session.get('customer_id')
    customer = Customer.objects.get(id=customer_id)
    
    active_loans = FinanceCreditSale.objects.filter(
        customer_id=customer_id,
        status__in=['ACTIVE', 'OVERDUE']
    ).order_by('-sale_date')
    
    closed_loans = FinanceCreditSale.objects.filter(
        customer_id=customer_id,
        status='CLOSED'
    ).order_by('-sale_date')[:5]
    
    total_outstanding = active_loans.aggregate(
        total=Sum('remaining_balance')
    )['total'] or 0
    
    total_paid = FinanceInstallment.objects.filter(
        customer_id=customer_id,
        status='PAID'
    ).aggregate(total=Sum('paid_total'))['total'] or 0
    
    context = {
        'customer': customer,
        'active_loans': active_loans,
        'closed_loans': closed_loans,
        'total_outstanding': total_outstanding,
        'total_paid': total_paid,
    }
    
    return render(request, 'portal/dashboard.html', context)


@customer_login_required
def loan_detail_view(request, loan_id):
    customer_id = request.session.get('customer_id')
    loan = FinanceCreditSale.objects.get(id=loan_id, customer_id=customer_id)
    installments = FinanceInstallment.objects.filter(sale=loan).order_by('installment_no', 'due_date')
    ledger = FinanceLedger.objects.filter(sale=loan).order_by('-entry_date')
    
    # Try to get motorcycle color and engine number from Motorcycle table using chassis_no
    motorcycle_color = None
    motorcycle_engine_no = None
    try:
        motorcycle = Motorcycle.objects.get(chassis_number=loan.chassis_no)
        motorcycle_color = motorcycle.color
        motorcycle_engine_no = motorcycle.engine_number
    except Motorcycle.DoesNotExist:
        pass
    
    context = {
        'customer': Customer.objects.get(id=customer_id),
        'loan': loan,
        'installments': installments,
        'ledger': ledger,
        'motorcycle_color': motorcycle_color,
        'motorcycle_engine_no': motorcycle_engine_no,
    }
    
    return render(request, 'portal/loan_detail.html', context)


@customer_login_required
def payments_view(request):
    customer_id = request.session.get('customer_id')
    customer = Customer.objects.get(id=customer_id)
    payments = FinanceInstallment.objects.filter(
        customer_id=customer_id
    ).order_by('-payment_date')[:50]
    
    context = {
        'customer': customer,
        'payments': payments,
    }
    
    return render(request, 'portal/payments.html', context)


@customer_login_required
def profile_view(request):
    customer_id = request.session.get('customer_id')
    customer = Customer.objects.get(id=customer_id)
    
    context = {
        'customer': customer,
    }
    
    return render(request, 'portal/profile.html', context)


@staff_member_required
def credit_customers_view(request):
    """Admin view showing all customers with credit sales."""
    customers = Customer.objects.annotate(
        total_credit_sales=Count('financecreditsale'),
        total_outstanding=Sum('financecreditsale__remaining_balance', filter=Q(financecreditsale__status__in=['ACTIVE', 'OVERDUE']))
    ).filter(total_credit_sales__gt=0).order_by('-total_credit_sales')
    
    context = {
        'title': 'Credit Customers',
        'customers': customers,
    }
    
    return render(request, 'portal/admin/credit_customers.html', context)


@staff_member_required
def custom_admin_dashboard_view(request):
    """Custom admin dashboard with statistics and overview."""
    today = timezone.now().date()
    
    total_customers = Customer.objects.filter(is_deleted=False).count()
    total_credit_customers = Customer.objects.annotate(
        credit_count=Count('financecreditsale')
    ).filter(credit_count__gt=0, is_deleted=False).count()
    
    total_sales = FinanceCreditSale.objects.count()
    total_outstanding = FinanceCreditSale.objects.filter(
        status__in=['ACTIVE', 'OVERDUE']
    ).aggregate(total=Sum('remaining_balance'))['total'] or 0
    
    total_paid = FinanceInstallment.objects.filter(
        status='PAID'
    ).aggregate(total=Sum('paid_total'))['total'] or 0
    
    recent_sales = FinanceCreditSale.objects.all().order_by('-sale_date')[:10]
    recent_payments = FinanceInstallment.objects.filter(status='PAID').order_by('-payment_date')[:10]
    
    sales_by_status = FinanceCreditSale.objects.values('status').annotate(
        count=Count('id'),
        total=Sum('remaining_balance')
    ).order_by('status')
    
    context = {
        'title': 'Admin Dashboard',
        'total_customers': total_customers,
        'total_credit_customers': total_credit_customers,
        'total_sales': total_sales,
        'total_outstanding': total_outstanding,
        'total_paid': total_paid,
        'recent_sales': recent_sales,
        'recent_payments': recent_payments,
        'sales_by_status': sales_by_status,
    }
    
    return render(request, 'portal/custom_admin/dashboard.html', context)


@staff_member_required
def custom_admin_customers_view(request):
    """Custom admin customers list - only shows customers with credit sales."""
    customers = Customer.objects.filter(is_deleted=False).annotate(
        credit_sales_count=Count('financecreditsale'),
        total_outstanding=Sum('financecreditsale__remaining_balance', filter=Q(financecreditsale__status__in=['ACTIVE', 'OVERDUE']))
    ).filter(credit_sales_count__gt=0).order_by('-id')
    
    context = {
        'title': 'Credit Customers',
        'customers': customers,
    }
    
    return render(request, 'portal/custom_admin/customers.html', context)


@staff_member_required
def custom_admin_sales_view(request):
    """Custom admin sales list."""
    sales = FinanceCreditSale.objects.select_related('customer').order_by('-sale_date')
    
    context = {
        'title': 'Credit Sales',
        'sales': sales,
    }
    
    return render(request, 'portal/custom_admin/sales.html', context)


@staff_member_required
def custom_admin_payments_view(request):
    """Custom admin payments list."""
    payments = FinanceInstallment.objects.select_related('customer', 'sale').order_by('-payment_date')
    
    context = {
        'title': 'Payments',
        'payments': payments,
    }
    
    return render(request, 'portal/custom_admin/payments.html', context)


@staff_member_required
def custom_admin_inventory_view(request):
    """Custom admin inventory management view."""
    motorcycles = Motorcycle.objects.select_related('product_model').order_by('-id')
    
    context = {
        'title': 'Inventory',
        'motorcycles': motorcycles,
    }
    
    return render(request, 'portal/custom_admin/inventory.html', context)


@staff_member_required
def custom_admin_transactions_view(request):
    """Custom admin transaction history view."""
    ledger_entries = FinanceLedger.objects.select_related('customer', 'sale').order_by('-entry_date')[:100]
    
    context = {
        'title': 'Transaction History',
        'ledger_entries': ledger_entries,
    }
    
    return render(request, 'portal/custom_admin/transactions.html', context)


@staff_member_required
def export_sales_csv(request):
    """Export credit sales to CSV."""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="credit_sales.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['ID', 'Sale ID', 'Customer', 'Chassis No', 'Status', 'Remaining Balance', 'Sale Date'])
    
    sales = FinanceCreditSale.objects.all().order_by('-sale_date')
    for sale in sales:
        writer.writerow([
            sale.id,
            sale.sale_id,
            sale.customer_name,
            sale.chassis_no,
            sale.status,
            sale.remaining_balance,
            sale.sale_date
        ])
    
    return response


@staff_member_required
def export_payments_csv(request):
    """Export payments to CSV."""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="payments.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['ID', 'Payment ID', 'Customer', 'Amount', 'Status', 'Payment Date'])
    
    payments = FinanceInstallment.objects.all().order_by('-payment_date')
    for payment in payments:
        writer.writerow([
            payment.id,
            payment.payment_id,
            payment.customer.name if payment.customer else '',
            payment.paid_total,
            payment.status,
            payment.payment_date
        ])
    
    return response


@staff_member_required
def custom_admin_portal_auths_view(request):
    """Custom admin view to list all customer portal accounts."""
    auths = CustomerPortalAuth.objects.select_related('customer').order_by('-created_at')
    context = {
        'title': 'Customer Portal Accounts',
        'auths': auths
    }
    return render(request, 'portal/custom_admin/portal_auths.html', context)


@staff_member_required
def custom_admin_create_portal_auth_view(request):
    """Custom admin view to create a new customer portal account."""
    credit_customers = Customer.objects.filter(
        is_deleted=False,
        id__in=FinanceCreditSale.objects.values_list('customer_id', flat=True).distinct()
    ).exclude(
        id__in=CustomerPortalAuth.objects.values_list('customer_id', flat=True)
    ).order_by('name')
    
    if request.method == 'POST':
        customer_id = request.POST.get('customer_id')
        if customer_id:
            customer = get_object_or_404(Customer, id=customer_id)
            CustomerPortalAuth.objects.create(
                customer=customer,
                phone_number=customer.phone or '',
                password_hash=make_password('123456789'),
                is_active=True
            )
            messages.success(request, f'Portal account created for {customer.name}!')
            return redirect('custom_admin_portal_auths')
    
    context = {
        'title': 'Create Portal Account',
        'credit_customers': credit_customers
    }
    return render(request, 'portal/custom_admin/create_portal_auth.html', context)


@staff_member_required
def custom_admin_reset_portal_password_view(request, auth_id):
    """Custom admin view to reset a customer's portal password."""
    auth = get_object_or_404(CustomerPortalAuth, id=auth_id)
    auth.password_hash = make_password('123456789')
    auth.save()
    messages.success(request, f'Password reset for {auth.customer.name}!')
    return redirect('custom_admin_portal_auths')


@staff_member_required
def custom_admin_toggle_portal_active_view(request, auth_id):
    """Custom admin view to block/unblock a customer's portal account."""
    auth = get_object_or_404(CustomerPortalAuth, id=auth_id)
    auth.is_active = not auth.is_active
    auth.save()
    status = 'activated' if auth.is_active else 'blocked'
    messages.success(request, f'Account {status} for {auth.customer.name}!')
    return redirect('custom_admin_portal_auths')

