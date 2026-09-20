from django.shortcuts import render, get_object_or_404
from django.db.models import Sum, Count, Q
from django.http import HttpResponse, JsonResponse
import csv
from .permissions import staff_required
from .models import (
    Customer, FinanceCreditSale, FinanceInstallment, FinanceLedger,
    CustomerPortalAuth, CreditSale, BuyerLedger, CreditSaleItem, CreditPayment,
)


@staff_required('view_customers')
def get_customer_data(request, customer_id):
    customer = get_object_or_404(Customer, id=customer_id)
    return JsonResponse({
        'phone': customer.phone,
        'cnic': customer.cnic,
    })


@staff_required('view_customers')
def credit_customers_view(request):
    customers = Customer.objects.annotate(
        total_credit_sales=Count('financecreditsale'),
        total_outstanding=Sum('financecreditsale__remaining_balance', filter=Q(financecreditsale__status__in=['ACTIVE', 'OVERDUE']))
    ).filter(total_credit_sales__gt=0).order_by('-total_credit_sales')

    context = {
        'title': 'Credit Customers',
        'customers': customers,
    }

    return render(request, 'portal/admin/credit_customers.html', context)


@staff_required('export_data')
def export_sales_csv(request):
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


@staff_required('export_data')
def export_payments_csv(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="payments.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'ID', 'Payment ID', 'Type', 'Customer', 'Description',
        'Amount', 'Status', 'Date'
    ])

    finance_installments = FinanceInstallment.objects.select_related('customer').order_by('-payment_date')
    old_credit_payments = CreditPayment.objects.select_related('customer').order_by('-payment_date')
    finance_ledger_payments = FinanceLedger.objects.select_related('customer').filter(credit__gt=0).order_by('-entry_date')
    buyer_ledger_payments = BuyerLedger.objects.select_related('customer').filter(credit__gt=0).order_by('-date')

    all_payments = []

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
