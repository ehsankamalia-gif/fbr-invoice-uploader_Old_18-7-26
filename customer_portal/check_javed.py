
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "customer_portal.settings")
django.setup()

from portal.models import Customer, FinanceCreditSale, CreditSale, CreditSaleItem, FinanceLedger, BuyerLedger

print("Looking for Javed Iqbal...")
customer = Customer.objects.filter(name__icontains='JAVED').first()
if customer:
    print(f"\nCustomer found: ID={customer.id}, Name={customer.name}")
    
    print("\n--- Finance Credit Sales ---")
    for sale in FinanceCreditSale.objects.filter(customer=customer):
        print(f"  ID: {sale.id}, Sale ID: {sale.sale_id}, Chassis: {sale.chassis_no}, Credit Price: {sale.credit_price}, Remaining: {sale.remaining_balance}, Status: {sale.status}")
        
    print("\n--- Old Credit Sales ---")
    for sale in CreditSale.objects.filter(customer=customer):
        print(f"  ID: {sale.id}, Total Credit: {sale.total_credit_price}, Remaining: {sale.remaining_amount}, Status: {sale.status}")
        items = CreditSaleItem.objects.filter(sale=sale)
        print(f"    Items count: {len(items)}")
        for item in items:
            print(f"      Chassis: {item.chassis_number}, Model: {item.model}, Credit Price: {item.credit_price}")
            
    print("\n--- Finance Ledger Entries ---")
    for entry in FinanceLedger.objects.filter(customer=customer):
        print(f"  ID: {entry.id}, Date: {entry.entry_date}, Debit: {entry.debit}, Credit: {entry.credit}, Description: {entry.description}")
        
    print("\n--- Buyer Ledger Entries ---")
    for entry in BuyerLedger.objects.filter(customer=customer):
        print(f"  ID: {entry.id}, Date: {entry.date}, Debit: {entry.debit}, Credit: {entry.credit}, Description: {entry.description}, Chassis: {entry.chassis_number}, Ref ID: {entry.reference_id}, Ref Type: {entry.reference_type}")
