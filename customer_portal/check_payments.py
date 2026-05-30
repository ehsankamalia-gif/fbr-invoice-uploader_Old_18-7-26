
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "customer_portal.settings")
django.setup()

from portal.models import (
    Customer, FinanceCreditSale, FinanceInstallment, CreditPayment, CreditSale
)

print("=== FinanceInstallment ===")
for p in FinanceInstallment.objects.all():
    print(f"ID: {p.id}, PaymentID: {p.payment_id}, Customer: {p.customer.name if p.customer else 'N/A'}, Amount: {p.paid_amount}")

print("\n=== CreditPayment ===")
for p in CreditPayment.objects.all():
    print(f"ID: {p.id}, Customer: {p.customer.name if p.customer else 'N/A'}, Amount: {p.amount}")
