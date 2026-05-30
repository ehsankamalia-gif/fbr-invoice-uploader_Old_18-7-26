
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "customer_portal.settings")
django.setup()

from portal.models import (
    Customer, FinanceCreditSale, FinanceInstallment, CreditPayment, 
    CreditSale, BuyerLedger, FinanceLedger
)

print("\n===== BUYER LEDGER ENTRIES ====")
for entry in BuyerLedger.objects.all():
    print(
        f"ID: {entry.id}, Date: {entry.date}, Customer: {entry.customer.name if entry.customer else 'N/A'}, "
        f"Debit: {entry.debit}, Credit: {entry.credit}, Desc: {entry.description}"
    )

print("\n===== FINANCE LEDGER ENTRIES ====")
for entry in FinanceLedger.objects.all():
    print(
        f"ID: {entry.id}, Date: {entry.entry_date}, Customer: {entry.customer.name if entry.customer else 'N/A'}, "
        f"Debit: {entry.debit}, Credit: {entry.credit}, Desc: {entry.description}"
    )

print("\n===== FINANCE INSTALLMENTS ====")
for p in FinanceInstallment.objects.all():
    print(
        f"ID: {p.id}, PaymentID: {p.payment_id}, Customer: {p.customer.name if p.customer else 'N/A'}, "
        f"Amount: {p.paid_amount}, Status: {p.status}"
    )

print("\n===== CREDIT PAYMENTS ====")
for p in CreditPayment.objects.all():
    print(
        f"ID: {p.id}, Customer: {p.customer.name if p.customer else 'N/A'}, Amount: {p.amount}"
    )
