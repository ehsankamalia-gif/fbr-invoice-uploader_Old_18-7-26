
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'customer_portal.settings')
django.setup()

from portal.models import Customer, CustomerPortalAuth, FinanceCreditSale

with open('db_check_output.txt', 'w', encoding='utf-8') as f:
    f.write("=== CustomerPortalAuth Records ===\n")
    auth_records = CustomerPortalAuth.objects.all()
    if auth_records:
        for auth in auth_records:
            f.write(f"ID: {auth.id}\n")
            f.write(f"  Customer: {auth.customer.name} (ID: {auth.customer.id})\n")
            f.write(f"  Phone Number: '{auth.phone_number}'\n")
            f.write(f"  Is Active: {auth.is_active}\n")
            f.write(f"  Created At: {auth.created_at}\n")
            f.write("---\n")
    else:
        f.write("No CustomerPortalAuth records found!\n")

    f.write("\n=== Customers with Credit Sales ===\n")
    credit_customer_ids = FinanceCreditSale.objects.values_list('customer_id', flat=True).distinct()
    credit_customers = Customer.objects.filter(id__in=credit_customer_ids)
    if credit_customers:
        for customer in credit_customers:
            f.write(f"ID: {customer.id}\n")
            f.write(f"  Name: {customer.name}\n")
            f.write(f"  Phone: '{customer.phone}'\n")
            f.write(f"  CNIC: {customer.cnic}\n")
            f.write("---\n")
    else:
        f.write("No customers with credit sales found!\n")

print("Output written to db_check_output.txt")
