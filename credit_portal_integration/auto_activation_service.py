
#!/usr/bin/env python
"""
Auto-Activation Service for Customer Portal
Completely separate - NO changes to existing application
Monitors for new credit sales and auto-activates portal access
"""
import os
import sys
import time
import random
import string
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "customer_portal"))

# Set up Django for customer portal access
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "customer_portal.settings")
import django
django.setup()

from django.contrib.auth.hashers import make_password
from portal.models import Customer, CustomerPortalAuth, FinanceCreditSale


class CreditPortalAutoActivationService:
    def __init__(self, check_interval_seconds=10):
        self.check_interval = check_interval_seconds
        self.last_checked_at = datetime.now() - timedelta(hours=1)
        print("=" * 60)
        print("   Credit Portal Auto-Activation Service")
        print("=" * 60)
        print(f"Checking every {self.check_interval} seconds")
        print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)
        print()

    def generate_random_password(self, length=8):
        """Generate a random secure password"""
        chars = string.ascii_letters + string.digits
        return ''.join(random.choice(chars) for _ in range(length))

    def check_new_credit_sales(self):
        """Check for new credit sales since last check"""
        try:
            new_sales = FinanceCreditSale.objects.filter(
                created_at__gte=self.last_checked_at
            ).order_by('created_at')

            if new_sales.count() > 0:
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Found {new_sales.count()} new credit sale(s)!")
                print("-" * 60)

                for sale in new_sales:
                    self.process_credit_sale(sale)

                self.last_checked_at = datetime.now()

        except Exception as e:
            print(f"\nERROR checking sales: {e}")

    def process_credit_sale(self, sale):
        """Process a single credit sale - activate portal if needed"""
        try:
            customer = sale.customer
            
            print(f"  Processing sale: {sale.sale_id}")
            print(f"  Customer: {customer.name} (ID: {customer.id})")
            print(f"  Phone: {customer.phone if customer.phone else 'NO PHONE!'}")
            
            # Check if customer already has portal auth
            existing_auth = CustomerPortalAuth.objects.filter(customer=customer).first()
            
            if existing_auth:
                print(f"  ✓ Customer already has portal access (Phone: {existing_auth.phone_number})")
                print("  Skipping activation...")
                print()
                return
            
            # Check if customer has phone number
            if not customer.phone:
                print(f"  ⚠ WARNING: Customer has NO PHONE NUMBER!")
                print(f"  Cannot activate portal access!")
                print()
                return
            
            # Generate random password
            password = self.generate_random_password()
            
            # Create portal auth
            auth = CustomerPortalAuth.objects.create(
                customer=customer,
                phone_number=customer.phone,
                password_hash=make_password(password),
                is_active=True
            )
            
            print(f"  ✅ SUCCESS: Portal access activated!")
            print(f"  =========================================")
            print(f"  CUSTOMER CREDENTIALS:")
            print(f"  =========================================")
            print(f"  Name: {customer.name}")
            print(f"  Phone Number (Login): {customer.phone}")
            print(f"  Password: {password}")
            print(f"  Portal URL: http://127.0.0.1:8000")
            print(f"  =========================================")
            print()
            
            # Save credentials to a file for staff reference
            self.save_credentials_to_file(customer, customer.phone, password, sale.sale_id)
            
        except Exception as e:
            print(f"  ❌ ERROR processing sale {sale.sale_id}: {e}")
            import traceback
            traceback.print_exc()
            print()

    def save_credentials_to_file(self, customer, phone, password, sale_id):
        """Save credentials to a secure file for staff"""
        try:
            creds_dir = project_root / "credit_portal_integration" / "generated_credentials"
            creds_dir.mkdir(exist_ok=True)
            
            filename = f"credentials_{customer.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            filepath = creds_dir / filename
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write("=" * 60 + "\n")
                f.write("           CUSTOMER PORTAL CREDENTIALS\n")
                f.write("=" * 60 + "\n")
                f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Sale ID: {sale_id}\n")
                f.write("-" * 60 + "\n")
                f.write(f"Customer Name: {customer.name}\n")
                f.write(f"Customer ID: {customer.id}\n")
                f.write(f"Phone Number: {phone}\n")
                f.write("-" * 60 + "\n")
                f.write(f"Login URL: http://127.0.0.1:8000\n")
                f.write(f"Username/Phone: {phone}\n")
                f.write(f"Password: {password}\n")
                f.write("=" * 60 + "\n")
            
            print(f"  ✓ Credentials saved to: {filename}")
            
        except Exception as e:
            print(f"  ⚠ Could not save credentials file: {e}")

    def run(self):
        """Run the service continuously"""
        print("Service is running... (Press Ctrl+C to stop)")
        print()
        
        try:
            while True:
                self.check_new_credit_sales()
                time.sleep(self.check_interval)
                
        except KeyboardInterrupt:
            print("\n")
            print("=" * 60)
            print("Service stopped by user")
            print("=" * 60)


def main():
    service = CreditPortalAutoActivationService(check_interval_seconds=10)
    service.run()


if __name__ == "__main__":
    main()
