
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
    ProductModel, Motorcycle, CustomerPortalAuth,
    CreditSale, BuyerLedger, CreditSaleItem, CreditPayment
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
    
    finance_active = FinanceCreditSale.objects.filter(
        customer_id=customer_id,
        status__in=['ACTIVE', 'OVERDUE']
    ).order_by('-sale_date')
    
    finance_closed = FinanceCreditSale.objects.filter(
        customer_id=customer_id,
        status='CLOSED'
    ).order_by('-sale_date')
    
    old_active = CreditSale.objects.filter(
        customer_id=customer_id,
        remaining_amount__gt=0
    ).order_by('-sale_date')
    
    old_closed = CreditSale.objects.filter(
        customer_id=customer_id,
        remaining_amount=0
    ).order_by('-sale_date')
    
    active_loans = []
    for loan in finance_active:
        active_loans.append({
            'type': 'finance',
            'id': loan.id,
            'chassis_no': loan.chassis_no,
            'sale_date': loan.sale_date,
            'total_price': loan.credit_price,
            'paid': loan.credit_price - loan.remaining_balance,
            'remaining': loan.remaining_balance,
            'status': loan.status,
        })
    for loan in old_active:
        # Get chassis number from CreditSaleItem
        credit_sale_items = CreditSaleItem.objects.filter(sale=loan)
        chassis_no = ''
        if credit_sale_items.exists():
            chassis_no = credit_sale_items.first().chassis_number
        
        active_loans.append({
            'type': 'old',
            'id': loan.id,
            'chassis_no': chassis_no,
            'sale_date': loan.sale_date,
            'total_price': loan.total_credit_price,
            'paid': loan.total_credit_price - loan.remaining_amount,
            'remaining': loan.remaining_amount,
            'status': 'ACTIVE',
        })
    active_loans.sort(key=lambda x: x['sale_date'], reverse=True)
    
    closed_loans = []
    for loan in finance_closed:
        closed_loans.append({
            'type': 'finance',
            'id': loan.id,
            'chassis_no': loan.chassis_no,
            'sale_date': loan.sale_date,
            'total_price': loan.credit_price,
        })
    for loan in old_closed:
        # Get chassis number from CreditSaleItem
        credit_sale_items = CreditSaleItem.objects.filter(sale=loan)
        chassis_no = ''
        if credit_sale_items.exists():
            chassis_no = credit_sale_items.first().chassis_number
        
        closed_loans.append({
            'type': 'old',
            'id': loan.id,
            'chassis_no': chassis_no,
            'sale_date': loan.sale_date,
            'total_price': loan.total_credit_price,
        })
    closed_loans.sort(key=lambda x: x['sale_date'], reverse=True)
    closed_loans = closed_loans[:5]
    
    total_outstanding = (
        sum(l['remaining'] for l in active_loans)
    )
    
    finance_payments = FinanceLedger.objects.filter(
        sale__customer_id=customer_id,
        credit__gt=0
    ).aggregate(total=Sum('credit'))['total'] or 0
    
    old_payments = BuyerLedger.objects.filter(
        customer_id=customer_id,
        credit__gt=0
    ).aggregate(total=Sum('credit'))['total'] or 0
    
    total_paid = finance_payments + old_payments
    
    context = {
        'customer': customer,
        'active_loans': active_loans,
        'closed_loans': closed_loans,
        'total_outstanding': total_outstanding,
        'total_paid': total_paid,
    }
    
    return render(request, 'portal/dashboard.html', context)


@customer_login_required
def loan_detail_view(request, loan_type, loan_id):
    customer_id = request.session.get('customer_id')
    customer = Customer.objects.get(id=customer_id)
    
    if loan_type == 'finance':
        loan = FinanceCreditSale.objects.get(id=loan_id, customer_id=customer_id)
        ledger_entries = FinanceLedger.objects.filter(sale=loan).order_by('entry_date', 'id')
        payment_entries = FinanceLedger.objects.filter(sale=loan, credit__gt=0).order_by('-entry_date', '-id')
        chassis_no = loan.chassis_no
        total_price = loan.credit_price
        loan_status = loan.status
    else:
        loan = CreditSale.objects.get(id=loan_id, customer_id=customer_id)
        # Get all CreditSaleItems for this loan to get all chassis numbers
        credit_sale_items = CreditSaleItem.objects.filter(sale=loan)
        chassis_numbers = [item.chassis_number for item in credit_sale_items if item.chassis_number]
        
        # Filter BuyerLedger to only include entries for this specific CreditSale or any of its chassis numbers
        query = Q(customer_id=customer_id)
        if chassis_numbers:
            query &= (Q(reference_id=loan.id) | Q(chassis_number__in=chassis_numbers))
        else:
            query &= Q(reference_id=loan.id)
        
        ledger_entries = BuyerLedger.objects.filter(query).order_by('date', 'id')
        
        # Now, deduplicate: if an entry has both reference_id=loan.id and a matching chassis_number, keep only one
        seen_ids = set()
        unique_ledger_entries = []
        for entry in ledger_entries:
            if entry.id not in seen_ids:
                seen_ids.add(entry.id)
                unique_ledger_entries.append(entry)
        ledger_entries = unique_ledger_entries
        
        payment_entries = BuyerLedger.objects.filter(query, credit__gt=0).order_by('-date', '-id')
        
        # Set chassis_no to first item's chassis number for template
        chassis_no = chassis_numbers[0] if chassis_numbers else ''
        
        total_price = loan.total_credit_price
        
        # Determine status based on remaining amount
        if loan.remaining_amount > 0:
            loan_status = 'ACTIVE'
        else:
            loan_status = 'CLOSED'
    
    # Calculate running balance for loan ledger
    balance = 0.0
    ledger_with_balance = []
    
    # For old loans, process entries with virtual initial debit if needed
    if loan_type == 'old':
        # Calculate sum of debits from existing ledger entries
        total_debits = sum(
            entry.debit 
            for entry in ledger_entries 
            if hasattr(entry, 'debit')
        )
        
        # Check if sum of debits matches total_credit_price (within 0.01 tolerance)
        has_sufficient_debits = abs(total_debits - loan.total_credit_price) < 0.01
        
        # Also check if there's a single entry with debit equal to total_credit_price
        has_initial_debit = any(
            hasattr(entry, 'debit') and abs(entry.debit - loan.total_credit_price) < 0.01
            for entry in ledger_entries
        )
        
        # Only add virtual entry if we don't have sufficient debits already
        if not has_sufficient_debits and not has_initial_debit:
            # Create a temporary object to mimic a ledger entry
            class VirtualLedgerEntry:
                def __init__(self, date, description, debit):
                    self.date = date
                    self.entry_date = date
                    self.description = description
                    self.debit = debit
                    self.credit = 0.0
            
            virtual_entry = VirtualLedgerEntry(
                date=loan.sale_date,
                description=f"Credit Sale - {chassis_no or 'Motorcycle'}",
                debit=loan.total_credit_price
            )
            # Prepend virtual entry to ledger entries
            ledger_entries = [virtual_entry] + list(ledger_entries)
    
    for entry in ledger_entries:
        if loan_type == 'old' and hasattr(entry, 'date'):
            entry.entry_date = entry.date
        balance += entry.debit - entry.credit
        ledger_with_balance.append({
            'entry': entry,
            'running_balance': balance
        })
    
    # Try to get motorcycle color and engine number from Motorcycle table using chassis_no
    motorcycle_color = None
    motorcycle_engine_no = None
    if chassis_no:
        try:
            motorcycle = Motorcycle.objects.get(chassis_number=chassis_no)
            motorcycle_color = motorcycle.color
            motorcycle_engine_no = motorcycle.engine_number
        except Motorcycle.DoesNotExist:
            pass
    
    context = {
        'customer': customer,
        'loan': loan,
        'loan_type': loan_type,
        'payment_entries': payment_entries,
        'ledger_with_balance': ledger_with_balance,
        'motorcycle_color': motorcycle_color,
        'motorcycle_engine_no': motorcycle_engine_no,
        'total_price': total_price,
        'chassis_no': chassis_no,
        'loan_status': loan_status,
    }
    
    return render(request, 'portal/loan_detail.html', context)


@customer_login_required
def payments_view(request):
    customer_id = request.session.get('customer_id')
    customer = Customer.objects.get(id=customer_id)
    
    # Get all credit entries (payments) from both ledgers
    finance_sales = FinanceCreditSale.objects.filter(customer_id=customer_id)
    finance_payments = FinanceLedger.objects.filter(
        sale__in=finance_sales,
        credit__gt=0
    ).order_by('-entry_date', '-id')
    
    old_payments = BuyerLedger.objects.filter(
        customer_id=customer_id,
        credit__gt=0
    ).order_by('-date', '-id')
    
    payment_entries = []
    for payment in finance_payments:
        payment_entries.append({
            'type': 'finance',
            'date': payment.entry_date,
            'description': payment.description or '',
            'amount': payment.credit,
            'chassis_no': payment.sale.chassis_no,
        })
    for payment in old_payments:
        payment_entries.append({
            'type': 'old',
            'date': payment.date,
            'description': payment.description or '',
            'amount': payment.credit,
            'chassis_no': payment.chassis_number or '',
        })
    payment_entries.sort(key=lambda x: x['date'], reverse=True)
    payment_entries = payment_entries[:100]
    
    # Calculate total paid
    total_paid = sum(p['amount'] for p in payment_entries)
    
    context = {
        'customer': customer,
        'payment_entries': payment_entries,
        'total_paid': total_paid,
    }
    
    return render(request, 'portal/payments.html', context)


@customer_login_required
def profile_view(request):
    customer_id = request.session.get('customer_id')
    customer = Customer.objects.get(id=customer_id)
    
    context = {
        'customer': customer
    }
    
    return render(request, 'portal/profile.html', context)


@customer_login_required
def running_ledger_view(request):
    customer_id = request.session.get('customer_id')
    customer = Customer.objects.get(id=customer_id)
    
    # Get all ledger entries from both ledgers
    finance_sales = FinanceCreditSale.objects.filter(customer_id=customer_id)
    finance_ledger = FinanceLedger.objects.filter(sale__in=finance_sales).order_by('entry_date', 'id')
    
    old_ledger = BuyerLedger.objects.filter(customer_id=customer_id).order_by('date', 'id')
    
    # Combine and sort ledger entries
    all_entries = []
    for entry in finance_ledger:
        all_entries.append({
            'type': 'finance',
            'entry': entry,
            'date': entry.entry_date,
            'id': entry.id,
        })
    for entry in old_ledger:
        entry.entry_date = entry.date
        all_entries.append({
            'type': 'old',
            'entry': entry,
            'date': entry.date,
            'id': entry.id,
        })
    all_entries.sort(key=lambda x: (x['date'], x['id']))
    
    # Calculate running balance
    balance = 0.0
    ledger_with_balance = []
    total_paid = 0.0
    for item in all_entries:
        entry = item['entry']
        balance += entry.debit - entry.credit
        if entry.credit > 0:
            total_paid += entry.credit
        ledger_with_balance.append({
            'type': item['type'],
            'entry': entry,
            'running_balance': balance
        })
    
    context = {
        'customer': customer,
        'ledger_with_balance': ledger_with_balance,
        'total_paid': total_paid
    }
    
    return render(request, 'portal/running_ledger.html', context)


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
        credit_count_finance=Count('financecreditsale'),
        credit_count_old=Count('creditsale__creditsaleitem')
    ).filter(
        Q(credit_count_finance__gt=0) | Q(credit_count_old__gt=0), 
        is_deleted=False
    ).count()
    
    total_finance_sales = FinanceCreditSale.objects.count()
    total_old_sales_items = CreditSaleItem.objects.count()
    total_sales = total_finance_sales + total_old_sales_items
    
    total_outstanding_finance = FinanceCreditSale.objects.filter(
        status__in=['ACTIVE', 'OVERDUE']
    ).aggregate(total=Sum('remaining_balance'))['total'] or 0
    total_outstanding_old = CreditSale.objects.filter(
        status__in=['ACTIVE', 'OVERDUE']
    ).aggregate(total=Sum('remaining_amount'))['total'] or 0
    total_outstanding = total_outstanding_finance + total_outstanding_old
    
    total_paid_finance = FinanceInstallment.objects.filter(
        status='PAID'
    ).aggregate(total=Sum('paid_amount'))['total'] or 0
    total_paid_old = BuyerLedger.objects.filter(
        credit__gt=0
    ).aggregate(total=Sum('credit'))['total'] or 0
    total_paid = total_paid_finance + total_paid_old
    
    recent_sales = FinanceCreditSale.objects.all().order_by('-sale_date')[:10]
    recent_payments = FinanceInstallment.objects.filter(status='PAID').order_by('-payment_date')[:10]
    
    sales_by_status = FinanceCreditSale.objects.values('status').annotate(
        count=Count('id'),
        total=Sum('remaining_balance')
    ).order_by('status')
    
    finance_chassis = FinanceCreditSale.objects.values_list('chassis_no', flat=True)
    credit_sale_items = CreditSaleItem.objects.values_list('chassis_number', flat=True)
    all_credit_chassis = list(finance_chassis) + list(credit_sale_items)
    
    motorcycles_by_model = Motorcycle.objects.filter(
        chassis_number__in=all_credit_chassis
    ).values(
        'product_model__id',
        'product_model__model_name'
    ).annotate(
        count=Count('id'),
        in_stock=Count('id', filter=Q(status=Motorcycle.IN_STOCK)),
        sold=Count('id', filter=Q(status=Motorcycle.SOLD))
    ).order_by('product_model__model_name')
    
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
        'motorcycles_by_model': motorcycles_by_model,
    }
    
    return render(request, 'portal/custom_admin/dashboard.html', context)


@staff_member_required
def custom_admin_customers_view(request):
    """Custom admin customers list - only shows customers with credit sales."""
    customers = Customer.objects.filter(is_deleted=False).order_by('-id')
    
    customers_with_data = []
    for customer in customers:
        # Calculate finance counts and outstanding
        finance_sales = FinanceCreditSale.objects.filter(customer=customer)
        count_finance = len(finance_sales)
        outstanding_finance = sum(sale.remaining_balance for sale in finance_sales)
        
        # Calculate old counts (items) and outstanding
        old_sales = CreditSale.objects.filter(customer=customer)
        count_old = 0
        outstanding_old = 0
        for sale in old_sales:
            items = CreditSaleItem.objects.filter(sale=sale)
            count_old += len(items)
            outstanding_old += sale.remaining_amount
        
        total_count = count_finance + count_old
        if total_count == 0:
            continue
            
        total_outstanding = outstanding_finance + outstanding_old
        
        customers_with_data.append({
            'customer': customer,
            'credit_sales_count': total_count,
            'total_outstanding': total_outstanding
        })
    
    context = {
        'title': 'Credit Customers',
        'customers': customers_with_data,
    }
    
    return render(request, 'portal/custom_admin/customers.html', context)


@staff_member_required
def custom_admin_sales_view(request):
    """Custom admin sales list."""
    finance_sales = FinanceCreditSale.objects.select_related('customer').order_by('-sale_date')
    old_sales = CreditSale.objects.select_related('customer').order_by('-sale_date')
    
    all_sales = []
    for sale in finance_sales:
        all_sales.append({
            'type': 'Finance',
            'id': sale.id,
            'sale_id': sale.sale_id,
            'customer_name': sale.customer_name,
            'chassis_no': sale.chassis_no,
            'status': sale.status,
            'remaining_balance': sale.remaining_balance,
            'sale_date': sale.sale_date,
        })
    for sale in old_sales:
        all_sales.append({
            'type': 'Old',
            'id': sale.id,
            'sale_id': None,
            'customer_name': sale.customer.name,
            'chassis_no': None,
            'status': sale.status,
            'remaining_balance': sale.remaining_amount,
            'sale_date': sale.sale_date,
        })
    all_sales.sort(key=lambda x: x['sale_date'], reverse=True)
    
    context = {
        'title': 'Credit Sales',
        'sales': all_sales,
    }
    
    return render(request, 'portal/custom_admin/sales.html', context)


@staff_member_required
def custom_admin_payments_view(request):
    """Custom admin payments list with all payment types from both systems (no duplicates)."""
    # Use only ledger entries as they are the source of truth
    finance_ledger_payments = FinanceLedger.objects.select_related('customer').filter(credit__gt=0).order_by('-entry_date')
    buyer_ledger_payments = BuyerLedger.objects.select_related('customer').filter(credit__gt=0).order_by('-date')
    
    # Combine all payments
    all_payments = []
    
    # Finance Ledger Payments
    for entry in finance_ledger_payments:
        all_payments.append({
            'id': entry.id,
            'type': 'Finance Payment',
            'payment_id': entry.ledger_id,
            'customer': entry.customer,
            'amount': entry.credit,
            'status': 'PAID',
            'date': entry.entry_date,
            'description': entry.description or 'Finance payment',
            'edit_url': f"/admin/portal/financeledger/{entry.id}/change/",
        })
    
    # Buyer Ledger Payments
    for entry in buyer_ledger_payments:
        all_payments.append({
            'id': entry.id,
            'type': 'Old System Payment',
            'payment_id': f"BUYER-LEDGER-{entry.id}",
            'customer': entry.customer,
            'amount': entry.credit,
            'status': 'PAID',
            'date': entry.date,
            'description': entry.description or 'Old system payment',
            'edit_url': f"/admin/portal/buyerledger/{entry.id}/change/",
        })
    
    # Sort all payments by date descending
    all_payments.sort(key=lambda x: x['date'], reverse=True)
    
    total_amount = sum(p['amount'] for p in all_payments)
    
    context = {
        'title': 'Payments',
        'payments': all_payments,
        'total_amount': total_amount,
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
    """Custom admin transaction history view with both ledgers."""
    finance_entries = FinanceLedger.objects.select_related('customer', 'sale').order_by('-entry_date')
    old_entries = BuyerLedger.objects.select_related('customer').order_by('-date')
    
    all_entries = []
    
    for entry in finance_entries:
        all_entries.append({
            'id': entry.id,
            'ledger_id': entry.ledger_id,
            'customer': entry.customer,
            'entry_type': entry.entry_type,
            'debit': entry.debit,
            'credit': entry.credit,
            'balance': entry.balance,
            'date': entry.entry_date,
        })
    
    for entry in old_entries:
        entry_type = 'DEBIT' if entry.debit > 0 else 'CREDIT'
        all_entries.append({
            'id': entry.id,
            'ledger_id': f"OLD-LEDGER-{entry.id}",
            'customer': entry.customer,
            'entry_type': entry_type,
            'debit': entry.debit,
            'credit': entry.credit,
            'balance': entry.balance,
            'date': entry.date,
        })
    
    # Sort all entries by date descending and take first 100
    all_entries.sort(key=lambda x: x['date'], reverse=True)
    all_entries = all_entries[:100]
    
    context = {
        'title': 'Transaction History',
        'ledger_entries': all_entries,
    }
    
    return render(request, 'portal/custom_admin/transactions.html', context)


@staff_member_required
def export_sales_csv(request):
    """Export credit sales to CSV with both Finance and Old System sales."""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="credit_sales.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['ID', 'Type', 'Sale ID', 'Customer', 'Chassis No', 'Status', 'Remaining Balance', 'Sale Date'])
    
    finance_sales = FinanceCreditSale.objects.all().order_by('-sale_date')
    old_sales = CreditSale.objects.all().order_by('-sale_date')
    
    all_sales = []
    for sale in finance_sales:
        all_sales.append({
            'id': sale.id,
            'type': 'Finance',
            'sale_id': sale.sale_id,
            'customer_name': sale.customer_name,
            'chassis_no': sale.chassis_no,
            'status': sale.status,
            'remaining_balance': sale.remaining_balance,
            'sale_date': sale.sale_date,
        })
    for sale in old_sales:
        all_sales.append({
            'id': sale.id,
            'type': 'Old',
            'sale_id': None,
            'customer_name': sale.customer.name,
            'chassis_no': None,
            'status': sale.status,
            'remaining_balance': sale.remaining_amount,
            'sale_date': sale.sale_date,
        })
    
    all_sales.sort(key=lambda x: x['sale_date'], reverse=True)
    
    for sale in all_sales:
        writer.writerow([
            sale['id'],
            sale['type'],
            sale['sale_id'],
            sale['customer_name'],
            sale['chassis_no'],
            sale['status'],
            sale['remaining_balance'],
            sale['sale_date']
        ])
    
    return response


@staff_member_required
def export_payments_csv(request):
    """Export all payments to CSV including installments, advances, down payments, etc."""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="payments.csv"'
    
    writer = csv.writer(response)
    writer.writerow([
        'ID', 'Payment ID', 'Type', 'Customer', 'Description', 
        'Amount', 'Status', 'Date'
    ])
    
    # Get all payment sources
    finance_installments = FinanceInstallment.objects.select_related('customer').order_by('-payment_date')
    old_credit_payments = CreditPayment.objects.select_related('customer').order_by('-payment_date')
    finance_ledger_payments = FinanceLedger.objects.select_related('customer').filter(credit__gt=0).order_by('-entry_date')
    buyer_ledger_payments = BuyerLedger.objects.select_related('customer').filter(credit__gt=0).order_by('-date')
    
    all_payments = []
    
    # Finance Installments
    for p in finance_installments:
        all_payments.append({
            'id': p.id,
            'payment_id': p.payment_id,
            'type': 'Finance Installment',
            'customer': p.customer,
            'description': f"Installment for {p.sale.sale_id if p.sale else 'N/A'}",
            'amount': p.paid_amount,
            'status': p.status,
            'date': p.payment_date,
        })
    
    # Old Credit Payments
    for p in old_credit_payments:
        all_payments.append({
            'id': p.id,
            'payment_id': f"PAY-OLD-{p.id}",
            'type': 'Old Credit Payment',
            'customer': p.customer,
            'description': 'Old system payment',
            'amount': p.amount,
            'status': 'PAID',
            'date': p.payment_date,
        })
    
    # Finance Ledger Payments (down payments, etc)
    for entry in finance_ledger_payments:
        all_payments.append({
            'id': entry.id,
            'payment_id': entry.ledger_id,
            'type': 'Finance Ledger',
            'customer': entry.customer,
            'description': entry.description,
            'amount': entry.credit,
            'status': 'PAID',
            'date': entry.entry_date,
        })
    
    # Buyer Ledger Payments (advance payments)
    for entry in buyer_ledger_payments:
        all_payments.append({
            'id': entry.id,
            'payment_id': f"BUYER-LEDGER-{entry.id}",
            'type': 'Old Ledger Payment',
            'customer': entry.customer,
            'description': entry.description,
            'amount': entry.credit,
            'status': 'PAID',
            'date': entry.date,
        })
    
    # Sort all payments by date descending
    all_payments.sort(key=lambda x: x['date'], reverse=True)
    
    for payment in all_payments:
        writer.writerow([
            payment['id'],
            payment['payment_id'],
            payment['type'],
            payment['customer'].name if payment['customer'] else '',
            payment['description'],
            payment['amount'],
            payment['status'],
            payment['date']
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


@staff_member_required
def custom_admin_customer_summary_view(request):
    """Custom admin view to show customer summary with bike count."""
    customers = Customer.objects.filter(is_deleted=False)
    
    search_query = request.GET.get('search', '')
    if search_query:
        customers = customers.filter(
            Q(name__icontains=search_query) | 
            Q(phone__icontains=search_query) | 
            Q(cnic__icontains=search_query)
        )
    
    customers_with_data = []
    for customer in customers:
        # Finance calculations
        finance_sales = FinanceCreditSale.objects.filter(customer=customer)
        total_bikes_finance = len(finance_sales)
        total_credit_finance = sum(sale.credit_price for sale in finance_sales)
        total_remaining_finance = sum(sale.remaining_balance for sale in finance_sales)
        
        # Old calculations (count items)
        old_sales = CreditSale.objects.filter(customer=customer)
        total_bikes_old = 0
        total_credit_old = 0
        total_remaining_old = 0
        for sale in old_sales:
            items = CreditSaleItem.objects.filter(sale=sale)
            total_bikes_old += len(items)
            total_credit_old += sale.total_credit_price
            total_remaining_old += sale.remaining_amount
        
        total_bikes = total_bikes_finance + total_bikes_old
        
        if total_bikes == 0:
            continue
            
        total_credit = total_credit_finance + total_credit_old
        total_remaining = total_remaining_finance + total_remaining_old
        
        total_paid_finance = FinanceLedger.objects.filter(
            customer=customer,
            credit__gt=0
        ).aggregate(total=Sum('credit'))['total'] or 0
        
        total_paid_old = BuyerLedger.objects.filter(
            customer=customer,
            credit__gt=0
        ).aggregate(total=Sum('credit'))['total'] or 0
        
        total_paid = total_paid_finance + total_paid_old
        
        if total_bikes_finance > 0 and total_bikes_old > 0:
            ledger_type = 'Combined'
        elif total_bikes_finance > 0:
            ledger_type = 'Finance'
        else:
            ledger_type = 'Old'
        
        customers_with_data.append({
            'customer': customer,
            'total_bikes': total_bikes,
            'total_credit': total_credit,
            'total_remaining': total_remaining,
            'total_paid': total_paid,
            'ledger_type': ledger_type
        })
    
    # Sort the customers
    customers_with_data.sort(
        key=lambda x: (-x['total_bikes'], -x['total_bikes'], x['customer'].name)
    )
    
    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.GET.get('ajax'):
        results = []
        for item in customers_with_data:
            results.append({
                'id': item['customer'].id,
                'name': item['customer'].name,
                'phone': item['customer'].phone or '-',
                'cnic': item['customer'].cnic or '-',
                'total_bikes': item['total_bikes'],
                'total_credit': float(item['total_credit']),
                'total_paid': float(item['total_paid']),
                'total_remaining': float(item['total_remaining']),
                'ledger_type': item['ledger_type'],
                'detail_url': f'/customer/{item["customer"].id}/',
                'ledger_url': f'/customer/{item["customer"].id}/ledger/'
            })
        return JsonResponse({'customers': results})
    
    context = {
        'title': 'Customer Summary',
        'customers_with_data': customers_with_data,
        'search_query': search_query,
    }
    
    return render(request, 'portal/custom_admin/customer_summary.html', context)


@staff_member_required
def custom_admin_customer_detail_view(request, customer_id):
    """Custom admin view to show customer detail."""
    customer = get_object_or_404(Customer, id=customer_id, is_deleted=False)
    
    finance_sales = FinanceCreditSale.objects.filter(customer=customer).order_by('-sale_date')
    old_sales = CreditSale.objects.filter(customer=customer).order_by('-sale_date')
    
    all_sales = []
    for sale in finance_sales:
        all_sales.append({
            'type': 'Finance',
            'id': sale.id,
            'sale_id': sale.sale_id,
            'chassis_no': sale.chassis_no,
            'credit_price': sale.credit_price,
            'remaining': sale.remaining_balance,
            'status': sale.status,
            'sale_date': sale.sale_date,
        })
    for sale in old_sales:
        all_sales.append({
            'type': 'Old',
            'id': sale.id,
            'sale_id': None,
            'chassis_no': None,
            'credit_price': sale.total_credit_price,
            'remaining': sale.remaining_amount,
            'status': sale.status,
            'sale_date': sale.sale_date,
        })
    all_sales.sort(key=lambda x: x['sale_date'], reverse=True)
    
    finance_payments = FinanceLedger.objects.filter(customer=customer, credit__gt=0).order_by('-entry_date', '-id')
    old_payments = BuyerLedger.objects.filter(customer=customer, credit__gt=0).order_by('-date', '-id')
    
    all_payments = []
    for payment in finance_payments:
        all_payments.append({
            'type': 'Finance',
            'ledger_id': payment.ledger_id,
            'date': payment.entry_date,
            'description': payment.description,
            'amount': payment.credit,
        })
    for payment in old_payments:
        all_payments.append({
            'type': 'Old',
            'ledger_id': payment.id,
            'date': payment.date,
            'description': payment.description,
            'amount': payment.credit,
        })
    all_payments.sort(key=lambda x: x['date'], reverse=True)
    
    total_credit_finance = finance_sales.aggregate(total=Sum('credit_price'))['total'] or 0
    total_credit_old = old_sales.aggregate(total=Sum('total_credit_price'))['total'] or 0
    total_credit = total_credit_finance + total_credit_old
    
    total_remaining_finance = finance_sales.aggregate(total=Sum('remaining_balance'))['total'] or 0
    total_remaining_old = old_sales.aggregate(total=Sum('remaining_amount'))['total'] or 0
    total_remaining = total_remaining_finance + total_remaining_old
    
    total_paid_finance = finance_payments.aggregate(total=Sum('credit'))['total'] or 0
    total_paid_old = old_payments.aggregate(total=Sum('credit'))['total'] or 0
    total_paid = total_paid_finance + total_paid_old
    
    context = {
        'title': f'Customer Detail - {customer.name}',
        'customer': customer,
        'all_sales': all_sales,
        'all_payments': all_payments,
        'total_paid': total_paid,
        'total_credit': total_credit,
        'total_remaining': total_remaining,
    }
    
    return render(request, 'portal/custom_admin/customer_detail.html', context)


@staff_member_required
def custom_admin_old_credit_ledger_view(request):
    """Custom admin view for Old Running Credit Ledger."""
    sales = CreditSale.objects.select_related('customer').order_by('-sale_date')
    
    context = {
        'title': 'Old Running Credit Ledger',
        'sales': sales,
    }
    
    return render(request, 'portal/custom_admin/old_credit_ledger.html', context)


@staff_member_required
def custom_admin_finance_credit_ledger_view(request):
    """Custom admin view for Advance Separate Finance Ledger."""
    sales = FinanceCreditSale.objects.select_related('customer').order_by('-sale_date')
    
    context = {
        'title': 'Advance Separate Finance Ledger',
        'sales': sales,
    }
    
    return render(request, 'portal/custom_admin/finance_credit_ledger.html', context)


@staff_member_required
def custom_admin_combined_credit_ledger_view(request):
    """Custom admin view for Combined Customer Ledger."""
    finance_sales = FinanceCreditSale.objects.select_related('customer').order_by('-sale_date')
    old_sales = CreditSale.objects.select_related('customer').order_by('-sale_date')
    
    all_sales = []
    for sale in finance_sales:
        all_sales.append({
            'type': 'Finance',
            'id': sale.id,
            'sale_id': sale.sale_id,
            'customer_name': sale.customer_name,
            'chassis_no': sale.chassis_no,
            'status': sale.status,
            'remaining': sale.remaining_balance,
            'credit_price': sale.credit_price,
            'sale_date': sale.sale_date,
        })
    for sale in old_sales:
        all_sales.append({
            'type': 'Old',
            'id': sale.id,
            'sale_id': None,
            'customer_name': sale.customer.name,
            'chassis_no': None,
            'status': sale.status,
            'remaining': sale.remaining_amount,
            'credit_price': sale.total_credit_price,
            'sale_date': sale.sale_date,
        })
    all_sales.sort(key=lambda x: x['sale_date'], reverse=True)
    
    context = {
        'title': 'Combined Customer Ledger',
        'sales': all_sales,
    }
    
    return render(request, 'portal/custom_admin/combined_credit_ledger.html', context)


@staff_member_required
def custom_admin_customer_ledger_view(request, customer_id):
    """Custom admin view for a specific customer's ledger."""
    customer = get_object_or_404(Customer, id=customer_id, is_deleted=False)
    
    finance_sales = FinanceCreditSale.objects.filter(customer=customer).order_by('sale_date')
    old_sales = CreditSale.objects.filter(customer=customer).order_by('sale_date')
    finance_payments = FinanceLedger.objects.filter(customer=customer, credit__gt=0).order_by('entry_date')
    old_payments = BuyerLedger.objects.filter(customer=customer, credit__gt=0).order_by('date')
    
    all_transactions = []
    
    for sale in finance_sales:
        all_transactions.append({
            'type': 'Finance Sale',
            'date': sale.sale_date,
            'description': f'Credit Sale - {sale.chassis_no}',
            'debit': sale.credit_price,
            'credit': 0,
        })
    for sale in old_sales:
        all_transactions.append({
            'type': 'Old Sale',
            'date': sale.sale_date,
            'description': f'Credit Sale',
            'debit': sale.total_credit_price,
            'credit': 0,
        })
    for payment in finance_payments:
        all_transactions.append({
            'type': 'Finance Payment',
            'date': payment.entry_date,
            'description': payment.description or 'Payment',
            'debit': 0,
            'credit': payment.credit,
        })
    for payment in old_payments:
        all_transactions.append({
            'type': 'Old Payment',
            'date': payment.date,
            'description': payment.description or 'Payment',
            'debit': 0,
            'credit': payment.credit,
        })
    
    all_transactions.sort(key=lambda x: x['date'])
    
    balance = 0
    for transaction in all_transactions:
        balance += transaction['debit'] - transaction['credit']
        transaction['balance'] = balance
    
    context = {
        'title': f'Customer Ledger - {customer.name}',
        'customer': customer,
        'transactions': all_transactions,
    }
    
    return render(request, 'portal/custom_admin/customer_ledger.html', context)

