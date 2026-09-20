"""Phase 1 JSON API for the Vue 3 SPA rewrite: customer portal (full vertical
slice) + admin dashboard (proves the pattern on the permission-gated side).

Read-only endpoints port the exact query/aggregation logic already used by
the server-rendered views in views.py - see portal/views.py for the
templates being replaced page-by-page (see the SPA rewrite plan)."""

from django.contrib.auth import authenticate, login as auth_login, logout as auth_login_out
from django.db.models import Sum, Count, Q
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .api_auth import CustomerPrincipal
from .api_permissions import IsCustomer, IsStaffMember, HasPortalPermission
from .forms import LoginForm
from .models import (
    Customer, FinanceCreditSale, FinanceInstallment, FinanceLedger,
    Motorcycle, CreditSale, CreditSaleItem, BuyerLedger,
    SpareLedgerTransaction,
)


# --- Shared session/auth endpoints ------------------------------------------

def _customer_payload(customer):
    return {
        'id': customer.id,
        'name': customer.name,
        'type': customer.type,
        'father_name': customer.father_name,
        'business_name': customer.business_name,
        'ntn': customer.ntn,
        'cnic': customer.cnic,
        'phone': customer.phone,
        'address': customer.address,
        'created_at': customer.created_at,
    }


def _user_payload(user):
    role = 'admin' if user.is_superuser else 'staff'
    # get_all_permissions() returns 'app_label.codename' strings, but every
    # other place a permission code is compared (STAFF_MODULES, route
    # meta.perm, HasPortalPermission's argument) uses the bare codename -
    # strip the 'portal.' prefix here so the frontend's `can(code)` getter
    # actually matches instead of silently never matching for staff users.
    permissions = [] if role == 'admin' else sorted(
        codename.split('.', 1)[1] for codename in user.get_all_permissions()
        if codename.startswith('portal.')
    )
    return {
        'id': user.id,
        'username': user.username,
        'role': role,
        'permissions': permissions,
    }


@api_view(['GET'])
@permission_classes([AllowAny])
def session_view(request):
    """'Who am I' - shared by both the customer portal and the admin app."""
    user = request.user

    if isinstance(user, CustomerPrincipal):
        return Response({'role': 'customer', 'customer': _customer_payload(user.customer)})

    if getattr(user, 'is_authenticated', False) and user.is_staff:
        payload = _user_payload(user)
        return Response({'role': payload['role'], 'user': payload})

    return Response({'role': 'anonymous'})


@api_view(['POST'])
@permission_classes([AllowAny])
def customer_login_view(request):
    form = LoginForm(request.data)
    if not form.is_valid():
        return Response({'errors': form.errors}, status=400)

    customer = form.cleaned_data['customer']
    request.session['customer_id'] = customer.id
    request.session['customer_name'] = customer.name
    request.session['customer_type'] = customer.type
    return Response({'customer': _customer_payload(customer)})


@api_view(['POST'])
@permission_classes([IsCustomer])
def customer_logout_view(request):
    request.session.flush()
    return Response({'ok': True})


@api_view(['POST'])
@permission_classes([AllowAny])
def staff_login_view(request):
    username = request.data.get('username', '')
    password = request.data.get('password', '')
    user = authenticate(request, username=username, password=password)

    if user is None:
        return Response({'errors': {'__all__': ['Invalid username or password.']}}, status=400)
    if not user.is_staff:
        return Response({'errors': {'__all__': ['This login is for staff and admin accounts only.']}}, status=400)

    auth_login(request, user)
    return Response({'user': _user_payload(user)})


@api_view(['POST'])
@permission_classes([IsStaffMember])
def staff_logout_view(request):
    auth_login_out(request)
    return Response({'ok': True})


# --- Customer portal ---------------------------------------------------------

@api_view(['GET'])
@permission_classes([IsCustomer])
def customer_dashboard_view(request):
    customer = request.user.customer
    customer_id = customer.id

    finance_active = FinanceCreditSale.objects.filter(
        customer_id=customer_id, status__in=['ACTIVE', 'OVERDUE']
    ).order_by('-sale_date')
    finance_closed = FinanceCreditSale.objects.filter(
        customer_id=customer_id, status='CLOSED'
    ).order_by('-sale_date')
    old_active = CreditSale.objects.filter(
        customer_id=customer_id, remaining_amount__gt=0
    ).order_by('-sale_date')
    old_closed = CreditSale.objects.filter(
        customer_id=customer_id, remaining_amount=0
    ).order_by('-sale_date')

    active_loans = []
    for loan in finance_active:
        active_loans.append({
            'type': 'finance', 'id': loan.id, 'chassis_no': loan.chassis_no,
            'sale_date': loan.sale_date, 'total_price': loan.credit_price,
            'paid': loan.credit_price - loan.remaining_balance,
            'remaining': loan.remaining_balance, 'status': loan.status,
        })
    for loan in old_active:
        item = CreditSaleItem.objects.filter(sale=loan).first()
        active_loans.append({
            'type': 'old', 'id': loan.id,
            'chassis_no': item.chassis_number if item else '',
            'sale_date': loan.sale_date, 'total_price': loan.total_credit_price,
            'paid': loan.total_credit_price - loan.remaining_amount,
            'remaining': loan.remaining_amount, 'status': 'ACTIVE',
        })
    active_loans.sort(key=lambda x: x['sale_date'], reverse=True)

    closed_loans = []
    for loan in finance_closed:
        closed_loans.append({
            'type': 'finance', 'id': loan.id, 'chassis_no': loan.chassis_no,
            'sale_date': loan.sale_date, 'total_price': loan.credit_price,
        })
    for loan in old_closed:
        item = CreditSaleItem.objects.filter(sale=loan).first()
        closed_loans.append({
            'type': 'old', 'id': loan.id,
            'chassis_no': item.chassis_number if item else '',
            'sale_date': loan.sale_date, 'total_price': loan.total_credit_price,
        })
    closed_loans.sort(key=lambda x: x['sale_date'], reverse=True)
    closed_loans = closed_loans[:5]

    total_outstanding = sum(l['remaining'] for l in active_loans)
    finance_payments = FinanceLedger.objects.filter(
        sale__customer_id=customer_id, credit__gt=0
    ).aggregate(total=Sum('credit'))['total'] or 0
    old_payments = BuyerLedger.objects.filter(
        customer_id=customer_id, credit__gt=0
    ).aggregate(total=Sum('credit'))['total'] or 0

    return Response({
        'customer': _customer_payload(customer),
        'active_loans': active_loans,
        'closed_loans': closed_loans,
        'total_outstanding': total_outstanding,
        'total_paid': finance_payments + old_payments,
    })


@api_view(['GET'])
@permission_classes([IsCustomer])
def customer_loan_detail_view(request, loan_type, loan_id):
    customer_id = request.user.customer.id

    if loan_type == 'finance':
        loan = FinanceCreditSale.objects.filter(id=loan_id, customer_id=customer_id).first()
        if loan is None:
            return Response({'detail': 'Not found.'}, status=404)
        ledger_entries = list(FinanceLedger.objects.filter(sale=loan).order_by('entry_date', 'id'))
        payment_entries = FinanceLedger.objects.filter(sale=loan, credit__gt=0).order_by('-entry_date', '-id')
        chassis_no = loan.chassis_no
        loan_status = loan.status
        loan_payload = {
            'id': loan.id, 'sale_id': loan.sale_id, 'sale_date': loan.sale_date,
            'due_date': loan.due_date, 'total_price': loan.credit_price,
            'remaining': loan.remaining_balance, 'cash_price': loan.cash_price,
            'credit_price': loan.credit_price, 'down_payment': loan.down_payment,
            'installment_amount': loan.installment_amount,
            'duration_months': loan.duration_months, 'duration_days': loan.duration_days,
        }
    else:
        loan = CreditSale.objects.filter(id=loan_id, customer_id=customer_id).first()
        if loan is None:
            return Response({'detail': 'Not found.'}, status=404)
        items = CreditSaleItem.objects.filter(sale=loan)
        chassis_numbers = [item.chassis_number for item in items if item.chassis_number]

        query = Q(customer_id=customer_id)
        query &= (Q(reference_id=loan.id) | Q(chassis_number__in=chassis_numbers)) if chassis_numbers else Q(reference_id=loan.id)

        seen_ids = set()
        ledger_entries = []
        for entry in BuyerLedger.objects.filter(query).order_by('date', 'id'):
            if entry.id not in seen_ids:
                seen_ids.add(entry.id)
                ledger_entries.append(entry)

        payment_entries = BuyerLedger.objects.filter(query, credit__gt=0).order_by('-date', '-id')
        chassis_no = chassis_numbers[0] if chassis_numbers else ''
        loan_status = 'ACTIVE' if loan.remaining_amount > 0 else 'CLOSED'
        loan_payload = {
            'id': loan.id, 'sale_id': loan.id, 'sale_date': loan.sale_date,
            'due_date': None, 'total_price': loan.total_credit_price,
            'remaining': loan.remaining_amount,
        }

        total_debits = sum(getattr(e, 'debit', 0) for e in ledger_entries)
        has_sufficient_debits = abs(total_debits - loan.total_credit_price) < 0.01
        has_initial_debit = any(abs(getattr(e, 'debit', 0) - loan.total_credit_price) < 0.01 for e in ledger_entries)
        if not has_sufficient_debits and not has_initial_debit:
            class VirtualEntry:
                def __init__(self, date, description, debit):
                    self.entry_date = date
                    self.description = description
                    self.debit = debit
                    self.credit = 0.0
            ledger_entries = [VirtualEntry(loan.sale_date, f"Credit Sale - {chassis_no or 'Motorcycle'}", loan.total_credit_price)] + ledger_entries

    balance = 0.0
    ledger_with_balance = []
    for entry in ledger_entries:
        entry_date = entry.entry_date if hasattr(entry, 'entry_date') else entry.date
        balance += entry.debit - entry.credit
        ledger_with_balance.append({
            'date': entry_date, 'description': entry.description,
            'debit': entry.debit, 'credit': entry.credit, 'running_balance': balance,
        })

    payment_history = []
    for entry in payment_entries:
        entry_date = entry.entry_date if hasattr(entry, 'entry_date') else entry.date
        payment_history.append({'date': entry_date, 'description': entry.description, 'amount': entry.credit})

    motorcycle_color = None
    motorcycle_engine_no = None
    if chassis_no:
        motorcycle = Motorcycle.objects.filter(chassis_number=chassis_no).first()
        if motorcycle:
            motorcycle_color = motorcycle.color
            motorcycle_engine_no = motorcycle.engine_number

    return Response({
        'loan_type': loan_type,
        'loan_status': loan_status,
        'loan': loan_payload,
        'chassis_no': chassis_no,
        'motorcycle_color': motorcycle_color,
        'motorcycle_engine_no': motorcycle_engine_no,
        'payment_entries': payment_history,
        'ledger_with_balance': ledger_with_balance,
    })


@api_view(['GET'])
@permission_classes([IsCustomer])
def customer_payments_view(request):
    customer_id = request.user.customer.id
    finance_sales = FinanceCreditSale.objects.filter(customer_id=customer_id)
    finance_payments = FinanceLedger.objects.filter(sale__in=finance_sales, credit__gt=0).order_by('-entry_date', '-id')
    old_payments = BuyerLedger.objects.filter(customer_id=customer_id, credit__gt=0).order_by('-date', '-id')

    entries = []
    for p in finance_payments:
        entries.append({'type': 'finance', 'date': p.entry_date, 'description': p.description or '', 'amount': p.credit, 'chassis_no': p.sale.chassis_no})
    for p in old_payments:
        entries.append({'type': 'old', 'date': p.date, 'description': p.description or '', 'amount': p.credit, 'chassis_no': p.chassis_number or ''})
    entries.sort(key=lambda x: x['date'], reverse=True)
    entries = entries[:100]

    return Response({'payment_entries': entries, 'total_paid': sum(e['amount'] for e in entries)})


@api_view(['GET'])
@permission_classes([IsCustomer])
def customer_profile_view(request):
    return Response({'customer': _customer_payload(request.user.customer)})


@api_view(['GET'])
@permission_classes([IsCustomer])
def customer_running_ledger_view(request):
    customer_id = request.user.customer.id
    finance_sales = FinanceCreditSale.objects.filter(customer_id=customer_id)
    finance_ledger = FinanceLedger.objects.filter(sale__in=finance_sales).order_by('entry_date', 'id')
    old_ledger = BuyerLedger.objects.filter(customer_id=customer_id).order_by('date', 'id')

    all_entries = []
    for e in finance_ledger:
        all_entries.append({'type': 'finance', 'date': e.entry_date, 'id': e.id, 'description': e.description, 'debit': e.debit, 'credit': e.credit})
    for e in old_ledger:
        all_entries.append({'type': 'old', 'date': e.date, 'id': e.id, 'description': e.description, 'debit': e.debit, 'credit': e.credit})
    all_entries.sort(key=lambda x: (x['date'], x['id']))

    balance = 0.0
    total_paid = 0.0
    ledger_with_balance = []
    for e in all_entries:
        balance += e['debit'] - e['credit']
        if e['credit'] > 0:
            total_paid += e['credit']
        ledger_with_balance.append({**e, 'running_balance': balance})

    return Response({'ledger_with_balance': ledger_with_balance, 'total_paid': total_paid})


# --- Admin ---------------------------------------------------------------

@api_view(['GET'])
@permission_classes([HasPortalPermission('view_dashboard')])
def admin_dashboard_view(request):
    total_customers = Customer.objects.filter(is_deleted=False).count()
    total_credit_customers = Customer.objects.annotate(
        credit_count_finance=Count('financecreditsale'),
        credit_count_old=Count('creditsale__creditsaleitem')
    ).filter(
        Q(credit_count_finance__gt=0) | Q(credit_count_old__gt=0), is_deleted=False
    ).count()

    total_sales = FinanceCreditSale.objects.count() + CreditSaleItem.objects.count()

    total_outstanding = (
        (FinanceCreditSale.objects.filter(status__in=['ACTIVE', 'OVERDUE']).aggregate(t=Sum('remaining_balance'))['t'] or 0)
        + (CreditSale.objects.filter(status__in=['ACTIVE', 'OVERDUE']).aggregate(t=Sum('remaining_amount'))['t'] or 0)
    )
    total_paid = (
        (FinanceInstallment.objects.filter(status='PAID').aggregate(t=Sum('paid_amount'))['t'] or 0)
        + (BuyerLedger.objects.filter(credit__gt=0).aggregate(t=Sum('credit'))['t'] or 0)
    )

    recent_sales = [
        {'id': s.id, 'customer_name': s.customer_name, 'status': s.status, 'sale_date': s.sale_date}
        for s in FinanceCreditSale.objects.all().order_by('-sale_date')[:10]
    ]
    recent_payments = [
        {'id': p.id, 'customer_name': p.customer.name, 'paid_amount': p.paid_amount, 'payment_date': p.payment_date}
        for p in FinanceInstallment.objects.filter(status='PAID').select_related('customer').order_by('-payment_date')[:10]
    ]

    sales_by_status = list(
        FinanceCreditSale.objects.values('status').annotate(count=Count('id'), total=Sum('remaining_balance')).order_by('status')
    )

    finance_chassis = FinanceCreditSale.objects.values_list('chassis_no', flat=True)
    credit_sale_chassis = CreditSaleItem.objects.values_list('chassis_number', flat=True)
    all_chassis = list(finance_chassis) + list(credit_sale_chassis)
    motorcycles_by_model = list(
        Motorcycle.objects.filter(chassis_number__in=all_chassis).values(
            'product_model__id', 'product_model__model_name'
        ).annotate(
            count=Count('id'),
            in_stock=Count('id', filter=Q(status=Motorcycle.IN_STOCK)),
            sold=Count('id', filter=Q(status=Motorcycle.SOLD)),
        ).order_by('product_model__model_name')
    )

    return Response({
        'total_customers': total_customers,
        'total_credit_customers': total_credit_customers,
        'total_sales': total_sales,
        'total_outstanding': total_outstanding,
        'total_paid': total_paid,
        'recent_sales': recent_sales,
        'recent_payments': recent_payments,
        'sales_by_status': sales_by_status,
        'motorcycles_by_model': motorcycles_by_model,
    })


# --- Admin: Phase 2 read-only reports --------------------------------------

@api_view(['GET'])
@permission_classes([HasPortalPermission('view_customers')])
def admin_customers_view(request):
    customers = Customer.objects.filter(is_deleted=False).order_by('-id')

    results = []
    for customer in customers:
        finance_sales = FinanceCreditSale.objects.filter(customer=customer)
        count_finance = len(finance_sales)
        outstanding_finance = sum(sale.remaining_balance for sale in finance_sales)

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

        results.append({
            'id': customer.id, 'name': customer.name, 'type': customer.type,
            'phone': customer.phone, 'cnic': customer.cnic,
            'credit_sales_count': total_count,
            'total_outstanding': outstanding_finance + outstanding_old,
        })

    return Response({'customers': results})


@api_view(['GET'])
@permission_classes([HasPortalPermission('view_customer_summary')])
def admin_customer_summary_view(request):
    customers = Customer.objects.filter(is_deleted=False)
    search_query = request.GET.get('search', '')
    if search_query:
        customers = customers.filter(
            Q(name__icontains=search_query) | Q(phone__icontains=search_query) | Q(cnic__icontains=search_query)
        )

    results = []
    for customer in customers:
        finance_sales = FinanceCreditSale.objects.filter(customer=customer)
        total_bikes_finance = len(finance_sales)
        total_credit_finance = sum(sale.credit_price for sale in finance_sales)
        total_remaining_finance = sum(sale.remaining_balance for sale in finance_sales)

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

        total_paid_finance = FinanceLedger.objects.filter(customer=customer, credit__gt=0).aggregate(t=Sum('credit'))['t'] or 0
        total_paid_old = BuyerLedger.objects.filter(customer=customer, credit__gt=0).aggregate(t=Sum('credit'))['t'] or 0

        if total_bikes_finance > 0 and total_bikes_old > 0:
            ledger_type = 'Combined'
        elif total_bikes_finance > 0:
            ledger_type = 'Finance'
        else:
            ledger_type = 'Old'

        results.append({
            'id': customer.id, 'name': customer.name, 'phone': customer.phone or '-', 'cnic': customer.cnic or '-',
            'total_bikes': total_bikes,
            'total_credit': total_credit_finance + total_credit_old,
            'total_paid': total_paid_finance + total_paid_old,
            'total_remaining': total_remaining_finance + total_remaining_old,
            'ledger_type': ledger_type,
        })

    results.sort(key=lambda x: (-x['total_bikes'], x['name']))
    return Response({'customers': results})


@api_view(['GET'])
@permission_classes([HasPortalPermission('view_customer_summary')])
def admin_customer_detail_view(request, customer_id):
    customer = Customer.objects.filter(id=customer_id, is_deleted=False).first()
    if customer is None:
        return Response({'detail': 'Not found.'}, status=404)

    finance_sales = FinanceCreditSale.objects.filter(customer=customer).order_by('-sale_date')
    old_sales = CreditSale.objects.filter(customer=customer).order_by('-sale_date')

    all_sales = []
    for sale in finance_sales:
        all_sales.append({
            'type': 'Finance', 'id': sale.id, 'sale_id': sale.sale_id, 'chassis_no': sale.chassis_no,
            'credit_price': sale.credit_price, 'remaining': sale.remaining_balance,
            'status': sale.status, 'sale_date': sale.sale_date,
        })
    for sale in old_sales:
        all_sales.append({
            'type': 'Old', 'id': sale.id, 'sale_id': None, 'chassis_no': None,
            'credit_price': sale.total_credit_price, 'remaining': sale.remaining_amount,
            'status': sale.status, 'sale_date': sale.sale_date,
        })
    all_sales.sort(key=lambda x: x['sale_date'], reverse=True)

    finance_payments = FinanceLedger.objects.filter(customer=customer, credit__gt=0).order_by('-entry_date', '-id')
    old_payments = BuyerLedger.objects.filter(customer=customer, credit__gt=0).order_by('-date', '-id')

    all_payments = []
    for p in finance_payments:
        all_payments.append({'type': 'Finance', 'ledger_id': p.ledger_id, 'date': p.entry_date, 'description': p.description, 'amount': p.credit})
    for p in old_payments:
        all_payments.append({'type': 'Old', 'ledger_id': p.id, 'date': p.date, 'description': p.description, 'amount': p.credit})
    all_payments.sort(key=lambda x: x['date'], reverse=True)

    total_credit = (finance_sales.aggregate(t=Sum('credit_price'))['t'] or 0) + (old_sales.aggregate(t=Sum('total_credit_price'))['t'] or 0)
    total_remaining = (finance_sales.aggregate(t=Sum('remaining_balance'))['t'] or 0) + (old_sales.aggregate(t=Sum('remaining_amount'))['t'] or 0)
    total_paid = (finance_payments.aggregate(t=Sum('credit'))['t'] or 0) + (old_payments.aggregate(t=Sum('credit'))['t'] or 0)

    return Response({
        'customer': {'id': customer.id, 'name': customer.name, 'phone': customer.phone, 'cnic': customer.cnic},
        'all_sales': all_sales,
        'all_payments': all_payments,
        'total_credit': total_credit,
        'total_remaining': total_remaining,
        'total_paid': total_paid,
    })


@api_view(['GET'])
@permission_classes([HasPortalPermission('view_customer_summary')])
def admin_customer_ledger_view(request, customer_id):
    customer = Customer.objects.filter(id=customer_id, is_deleted=False).first()
    if customer is None:
        return Response({'detail': 'Not found.'}, status=404)

    finance_entries = FinanceLedger.objects.filter(customer=customer).order_by('entry_date')
    old_entries = BuyerLedger.objects.filter(customer=customer).order_by('date')

    all_transactions = []
    for e in finance_entries:
        all_transactions.append({'type': 'Finance Ledger', 'date': e.entry_date, 'description': e.description or 'Transaction', 'debit': e.debit or 0, 'credit': e.credit or 0})
    for e in old_entries:
        all_transactions.append({'type': 'Old Ledger', 'date': e.date, 'description': e.description or 'Transaction', 'debit': e.debit or 0, 'credit': e.credit or 0})
    all_transactions.sort(key=lambda x: x['date'])

    balance = 0
    for t in all_transactions:
        balance += t['debit'] - t['credit']
        t['balance'] = balance

    return Response({
        'customer': {'id': customer.id, 'name': customer.name, 'phone': customer.phone, 'cnic': customer.cnic},
        'transactions': all_transactions,
    })


@api_view(['GET'])
@permission_classes([HasPortalPermission('view_sales')])
def admin_sales_view(request):
    finance_sales = FinanceCreditSale.objects.select_related('customer').order_by('-sale_date')
    old_sales = CreditSale.objects.select_related('customer').order_by('-sale_date')

    all_sales = []
    for sale in finance_sales:
        all_sales.append({
            'type': 'Finance', 'id': sale.id, 'sale_id': sale.sale_id, 'customer_name': sale.customer_name,
            'chassis_no': sale.chassis_no, 'status': sale.status,
            'remaining_balance': sale.remaining_balance, 'sale_date': sale.sale_date,
        })
    for sale in old_sales:
        all_sales.append({
            'type': 'Old', 'id': sale.id, 'sale_id': None, 'customer_name': sale.customer.name,
            'chassis_no': None, 'status': sale.status,
            'remaining_balance': sale.remaining_amount, 'sale_date': sale.sale_date,
        })
    all_sales.sort(key=lambda x: x['sale_date'], reverse=True)
    return Response({'sales': all_sales})


@api_view(['GET'])
@permission_classes([HasPortalPermission('view_payments')])
def admin_payments_view(request):
    finance_ledger_payments = FinanceLedger.objects.select_related('customer').filter(credit__gt=0).order_by('-entry_date')
    buyer_ledger_payments = BuyerLedger.objects.select_related('customer').filter(credit__gt=0).order_by('-date')

    all_payments = []
    for entry in finance_ledger_payments:
        all_payments.append({
            'id': entry.id, 'type': 'Finance Payment', 'payment_id': entry.ledger_id,
            'customer_name': entry.customer.name, 'amount': entry.credit, 'status': 'PAID',
            'date': entry.entry_date, 'description': entry.description or 'Finance payment',
            'editable': True,
        })
    for entry in buyer_ledger_payments:
        all_payments.append({
            'id': entry.id, 'type': 'Old System Payment', 'payment_id': f'BUYER-LEDGER-{entry.id}',
            'customer_name': entry.customer.name, 'amount': entry.credit, 'status': 'PAID',
            'date': entry.date, 'description': entry.description or 'Old system payment',
            'editable': False,
        })
    all_payments.sort(key=lambda x: x['date'], reverse=True)

    return Response({'payments': all_payments, 'total_amount': sum(p['amount'] for p in all_payments)})


@api_view(['GET'])
@permission_classes([HasPortalPermission('view_inventory')])
def admin_inventory_view(request):
    motorcycles = Motorcycle.objects.select_related('product_model').order_by('-id')
    results = [
        {
            'id': m.id, 'chassis_number': m.chassis_number, 'engine_number': m.engine_number,
            'model_name': m.product_model.model_name if m.product_model else '',
            'color': m.color, 'status': m.status,
        }
        for m in motorcycles
    ]
    return Response({'motorcycles': results})


@api_view(['GET'])
@permission_classes([HasPortalPermission('view_transactions')])
def admin_transactions_view(request):
    finance_entries = FinanceLedger.objects.select_related('customer', 'sale').order_by('-entry_date')
    old_entries = BuyerLedger.objects.select_related('customer').order_by('-date')

    all_entries = []
    for entry in finance_entries:
        all_entries.append({
            'id': entry.id, 'ledger_id': entry.ledger_id, 'customer_name': entry.customer.name,
            'entry_type': entry.entry_type, 'debit': entry.debit, 'credit': entry.credit,
            'balance': entry.balance, 'date': entry.entry_date,
        })
    for entry in old_entries:
        all_entries.append({
            'id': entry.id, 'ledger_id': f'OLD-LEDGER-{entry.id}', 'customer_name': entry.customer.name,
            'entry_type': 'DEBIT' if entry.debit > 0 else 'CREDIT',
            'debit': entry.debit, 'credit': entry.credit, 'balance': entry.balance, 'date': entry.date,
        })
    all_entries.sort(key=lambda x: x['date'], reverse=True)
    return Response({'ledger_entries': all_entries[:100]})


@api_view(['GET'])
@permission_classes([HasPortalPermission('view_old_credit_ledger')])
def admin_old_credit_ledger_view(request):
    sales = CreditSale.objects.select_related('customer').order_by('-sale_date')
    results = [
        {
            'id': s.id, 'customer_name': s.customer.name, 'credit_price': s.total_credit_price,
            'remaining': s.remaining_amount, 'status': s.status, 'sale_date': s.sale_date,
        }
        for s in sales
    ]
    return Response({'sales': results})


@api_view(['GET'])
@permission_classes([HasPortalPermission('view_finance_credit_ledger')])
def admin_finance_credit_ledger_view(request):
    sales = FinanceCreditSale.objects.select_related('customer').order_by('-sale_date')
    results = [
        {
            'id': s.id, 'sale_id': s.sale_id, 'customer_name': s.customer_name, 'chassis_no': s.chassis_no,
            'credit_price': s.credit_price, 'remaining_balance': s.remaining_balance,
            'status': s.status, 'sale_date': s.sale_date,
        }
        for s in sales
    ]
    return Response({'sales': results})


@api_view(['GET'])
@permission_classes([HasPortalPermission('view_combined_ledger')])
def admin_combined_ledger_view(request):
    finance_sales = FinanceCreditSale.objects.select_related('customer').order_by('-sale_date')
    old_sales = CreditSale.objects.select_related('customer').order_by('-sale_date')

    all_sales = []
    for sale in finance_sales:
        all_sales.append({
            'type': 'Finance', 'id': sale.id, 'sale_id': sale.sale_id, 'customer_name': sale.customer_name,
            'chassis_no': sale.chassis_no, 'status': sale.status,
            'remaining': sale.remaining_balance, 'credit_price': sale.credit_price, 'sale_date': sale.sale_date,
        })
    for sale in old_sales:
        all_sales.append({
            'type': 'Old', 'id': sale.id, 'sale_id': None, 'customer_name': sale.customer.name,
            'chassis_no': None, 'status': sale.status,
            'remaining': sale.remaining_amount, 'credit_price': sale.total_credit_price, 'sale_date': sale.sale_date,
        })
    all_sales.sort(key=lambda x: x['sale_date'], reverse=True)
    return Response({'sales': all_sales})


def _spare_ledger_base_queryset():
    return SpareLedgerTransaction.objects.filter(
        Q(description__isnull=True) | ~Q(description__startswith='Advance Booking -')
    )


@api_view(['GET'])
@permission_classes([HasPortalPermission('view_spare_ledger')])
def admin_spare_ledger_transactions_view(request):
    selected_month = request.GET.get('month') or ''
    selected_trans_type = request.GET.get('trans_type') or ''

    transactions = _spare_ledger_base_queryset().order_by('timestamp')
    if selected_month:
        transactions = transactions.filter(month_key=selected_month)
    if selected_trans_type:
        transactions = transactions.filter(trans_type=selected_trans_type)

    total_credits = 0.0
    total_debits = 0.0
    for tx in transactions:
        amount = float(tx.amount or 0)
        if tx.trans_type == 'CREDIT':
            total_credits += amount
        else:
            total_debits += amount

    running_balance = 0.0
    rows = []
    for tx in transactions:
        amount = float(tx.amount or 0)
        running_balance += amount if tx.trans_type == 'CREDIT' else -amount
        rows.append({
            'timestamp': tx.timestamp,
            'cash_type_display': tx.get_cash_type_display(),
            'reference_number': tx.reference_number,
            'description': tx.description,
            'trans_type': tx.trans_type,
            'amount': tx.amount,
            'month_key': tx.month_key,
            'balance': running_balance,
        })

    unique_months = sorted(_spare_ledger_base_queryset().values_list('month_key', flat=True).distinct())

    return Response({
        'total_credits': total_credits,
        'total_debits': total_debits,
        'closing_balance': total_credits - total_debits,
        'transactions': rows,
        'unique_months': [m for m in unique_months if m],
        'selected_month': selected_month,
        'selected_trans_type': selected_trans_type,
    })


@api_view(['GET'])
@permission_classes([HasPortalPermission('view_spare_ledger')])
def admin_spare_ledger_monthly_report_view(request):
    transactions = _spare_ledger_base_queryset().order_by('timestamp')

    month_stats = {}
    for tx in transactions:
        key = tx.month_key or 'N/A'
        stats = month_stats.setdefault(key, {'bank_credit': 0.0, 'hard_cash_credit': 0.0, 'bank_debit': 0.0, 'hard_cash_debit': 0.0})
        amount = float(tx.amount or 0)
        is_bank = tx.cash_type == 'BANK'
        if tx.trans_type == 'CREDIT':
            stats['bank_credit' if is_bank else 'hard_cash_credit'] += amount
        else:
            stats['bank_debit' if is_bank else 'hard_cash_debit'] += amount

    report_data = []
    running_bf = 0.0
    for month_key in sorted(month_stats.keys()):
        stats = month_stats[month_key]
        total_in = stats['bank_credit'] + stats['hard_cash_credit']
        total_out = stats['bank_debit'] + stats['hard_cash_debit']
        closing_balance = running_bf + total_in - total_out
        report_data.append({
            'month_key': month_key, 'brought_forward': running_bf,
            'bank_credit': stats['bank_credit'], 'hard_cash_credit': stats['hard_cash_credit'], 'total_credit': total_in,
            'bank_debit': stats['bank_debit'], 'hard_cash_debit': stats['hard_cash_debit'], 'total_debit': total_out,
            'closing_balance': closing_balance, 'carried_forward': closing_balance,
        })
        running_bf = closing_balance

    return Response({
        'report_data': report_data,
        'grand_total_in': sum(r['total_credit'] for r in report_data),
        'grand_total_out': sum(r['total_debit'] for r in report_data),
        'overall_balance': running_bf,
    })


@api_view(['GET'])
@permission_classes([HasPortalPermission('view_spare_ledger')])
def admin_spare_ledger_monthly_summary_view(request):
    transactions = _spare_ledger_base_queryset().order_by('timestamp')

    month_stats = {}
    for tx in transactions:
        key = tx.month_key or 'N/A'
        stats = month_stats.setdefault(key, {'bank_credit': 0.0, 'hard_cash_credit': 0.0, 'total_debit': 0.0})
        amount = float(tx.amount or 0)
        is_bank = tx.cash_type == 'BANK'
        if tx.trans_type == 'CREDIT':
            stats['bank_credit' if is_bank else 'hard_cash_credit'] += amount
        else:
            stats['total_debit'] += amount

    report_data = []
    running_balance = 0.0
    for month_key in sorted(month_stats.keys()):
        stats = month_stats[month_key]
        total_credit = stats['bank_credit'] + stats['hard_cash_credit']
        monthly_balance = running_balance + total_credit - stats['total_debit']
        report_data.append({
            'date': month_key, 'previous_month_balance': running_balance,
            'bank_credit': stats['bank_credit'], 'cash_credit': stats['hard_cash_credit'],
            'sp_order': stats['total_debit'], 'monthly_balance': monthly_balance,
        })
        running_balance = monthly_balance

    current_balance = report_data[-1]['monthly_balance'] if report_data else 0.0
    return Response({'report_data': report_data, 'current_balance': current_balance})
