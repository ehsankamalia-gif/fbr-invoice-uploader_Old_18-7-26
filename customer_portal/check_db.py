
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'customer_portal.settings')
django.setup()

from portal.models import Customer, CustomerPortalAuth, FinanceCreditSale

print("=== CustomerPortalAuth Records ===")
auth_records = CustomerPortalAuth.objects.all()
if auth_records:
    for auth in auth_records:
        print(f"ID: {auth.id}")
        print(f"  Customer: {auth.customer.name} (ID: {auth.customer.id})")
        print(f"  Phone Number: '{auth.phone_number}'")
        print(f"  Is Active: {auth.is_active}")
        print(f"  Created At: {auth.created_at}")
        print("---")
else:
    print("No CustomerPortalAuth records found!")

print("\n=== Customers with Credit Sales ===")
credit_customer_ids = FinanceCreditSale.objects.values_list('customer_id', flat=True).distinct()
credit_customers = Customer.objects.filter(id__in=credit_customer_ids)
if credit_customers:
    for customer in credit_customers:
        print(f"ID: {customer.id}")
        print(f"  Name: {customer.name}")
        print(f"  Phone: '{customer.phone}'")
        print(f"  CNIC: {customer.cnic}")
        print("---")
else:
    print("No customers with credit sales found!")
