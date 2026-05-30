
import os
import django
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
print("Python path:", sys.path)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "customer_portal.settings")

try:
    django.setup()
    from portal.models import (
        FinanceCreditSale,
        FinanceInstallment,
        FinanceLedger,
        CreditSale,
        CreditSaleItem,
        BuyerLedger
    )
    print("✅ Models imported successfully!")

    print("\nDeleting finance_installments...")
    count_fin_installments = FinanceInstallment.objects.count()
    FinanceInstallment.objects.all().delete()
    print(f"✅ Deleted {count_fin_installments} finance_installments")

    print("\nDeleting finance_ledger...")
    count_fin_ledger = FinanceLedger.objects.count()
    FinanceLedger.objects.all().delete()
    print(f"✅ Deleted {count_fin_ledger} finance_ledger")

    print("\nDeleting credit_sale_items...")
    count_credit_items = CreditSaleItem.objects.count()
    CreditSaleItem.objects.all().delete()
    print(f"✅ Deleted {count_credit_items} credit_sale_items")

    print("\nDeleting buyer_ledger...")
    count_buyer_ledger = BuyerLedger.objects.count()
    BuyerLedger.objects.all().delete()
    print(f"✅ Deleted {count_buyer_ledger} buyer_ledger")

    print("\nDeleting credit_sales...")
    count_credit_sales = CreditSale.objects.count()
    CreditSale.objects.all().delete()
    print(f"✅ Deleted {count_credit_sales} credit_sales")

    print("\nDeleting finance_credit_sales...")
    count_fin_sales = FinanceCreditSale.objects.count()
    FinanceCreditSale.objects.all().delete()
    print(f"✅ Deleted {count_fin_sales} finance_credit_sales")

    print("\n✅ All credit-related tables emptied successfully!")

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    print(traceback.format_exc())
