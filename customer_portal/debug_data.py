
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "customer_portal.settings")
django.setup()

from portal.models import (
    Customer, FinanceCreditSale, CreditSale, CreditSaleItem, 
    FinanceLedger, BuyerLedger, FinanceInstallment
)

print("=== Debugging Data ===\n")

customers = Customer.objects.filter(name__in=['JAVED IQBAL', 'TAHIR'])
for customer in customers:
    print(f"Customer: {customer.name} (ID: {customer.id})")
    
    print("\n--- Finance Credit Sales ---")
    for sale in FinanceCreditSale.objects.filter(customer=customer):
        print(f"  Sale ID: {sale.id}, Chassis: {sale.chassis_no}, Credit Price: {sale.credit_price:.2f}, Remaining: {sale.remaining_balance:.2f}, Status: {sale.status}")
        
    print("\n--- Old Credit Sales ---")
    for sale in CreditSale.objects.filter(customer=customer):
        print(f"  Sale ID: {sale.id}, Total Credit: {sale.total_credit_price:.2f}, Remaining: {sale.remaining_amount:.2f}, Status: {sale.status}")
        items = CreditSaleItem.objects.filter(sale=sale)
        for item in items:
            print(f"    Item Chassis: {item.chassis_number}, Credit Price: {item.credit_price:.2f}")
            
    print("\n--- Finance Installments (Paid) ---")
    paid_finance = FinanceInstallment.objects.filter(customer=customer, status='PAID')
    total_paid_finance = sum(inst.paid_amount for inst in paid_finance)
    print(f"  Total Paid: {total_paid_finance:.2f}")
    for inst in paid_finance[:3]:
        print(f"    Installment ID: {inst.id}, Paid: {inst.paid_amount:.2f}")
        
    print("\n--- Finance Ledger (Credits) ---")
    finance_credits = FinanceLedger.objects.filter(customer=customer, credit__gt=0)
    total_credits_finance = sum(ent.credit for ent in finance_credits)
    print(f"  Total Credits: {total_credits_finance:.2f}")
    
    print("\n--- Buyer Ledger ---")
    buyer_entries = BuyerLedger.objects.filter(customer=customer)
    total_debits_buyer = sum(ent.debit for ent in buyer_entries)
    total_credits_buyer = sum(ent.credit for ent in buyer_entries)
    print(f"  Total Debits: {total_debits_buyer:.2f}, Total Credits: {total_credits_buyer:.2f}")
    for ent in buyer_entries[:5]:
        print(f"    Entry ID: {ent.id}, Date: {ent.date}, Debit: {ent.debit:.2f}, Credit: {ent.credit:.2f}, Chassis: {ent.chassis_number}, Ref ID: {ent.reference_id}")
        
    print("\n--- Calculated Outstanding ---")
    total_outstanding_finance = sum(
        sale.remaining_balance for sale in FinanceCreditSale.objects.filter(customer=customer)
    )
    total_outstanding_old = sum(
        sale.remaining_amount for sale in CreditSale.objects.filter(customer=customer)
    )
    print(f"  Finance Outstanding: {total_outstanding_finance:.2f}")
    print(f"  Old Outstanding: {total_outstanding_old:.2f}")
    print(f"  Total Outstanding: {total_outstanding_finance + total_outstanding_old:.2f}")
    
    print("\n" + "="*80 + "\n")
