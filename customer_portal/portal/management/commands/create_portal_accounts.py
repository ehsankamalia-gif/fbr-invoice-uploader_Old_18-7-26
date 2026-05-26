
from django.core.management.base import BaseCommand
from django.contrib.auth.hashers import make_password
from portal.models import Customer, CustomerPortalAuth, FinanceCreditSale
import random
import string
from django.db import connection


def generate_password(length=8):
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for _ in range(length))


class Command(BaseCommand):
    help = 'Create portal accounts for all customers with credit sales'

    def handle(self, *args, **options):
        self.stdout.write('Creating portal accounts for existing customers...\n')
        self.stdout.write('-' * 60 + '\n')

        created_count = 0
        already_exists_count = 0
        skipped_count = 0

        # Get all customers who have either old credit sales or finance credit sales
        customer_ids = []

        with connection.cursor() as cursor:
            # Get customers with finance credit sales (filter out NULL customer_id)
            cursor.execute("""
                SELECT DISTINCT customer_id 
                FROM finance_credit_sales
                WHERE customer_id IS NOT NULL
            """)
            finance_customer_ids = [row[0] for row in cursor.fetchall() if row[0]]
            customer_ids.extend(finance_customer_ids)

            # Get customers with old credit sales (if that table exists)
            try:
                cursor.execute("""
                    SELECT DISTINCT buyer_id 
                    FROM credit_sales
                    WHERE buyer_id IS NOT NULL
                """)
                old_customer_ids = [row[0] for row in cursor.fetchall() if row[0]]
                customer_ids.extend(old_customer_ids)
            except Exception:
                pass

        # Combine and deduplicate
        all_customer_ids = list(set(customer_ids))
        self.stdout.write(f'Found {len(all_customer_ids)} customers with credit sales\n\n')

        for customer_id in all_customer_ids:
            try:
                customer = Customer.objects.get(id=customer_id)
                
                # Check if portal auth already exists
                existing_auth = CustomerPortalAuth.objects.filter(customer_id=customer_id).first()
                
                if existing_auth:
                    self.stdout.write(
                        f'  [SKIP] Customer {customer.name} (ID: {customer_id}) already has a portal account\n'
                    )
                    already_exists_count += 1
                    continue

                # Determine phone number
                phone_number = customer.phone
                if not phone_number:
                    self.stdout.write(
                        f'  [WARN] Customer {customer.name} (ID: {customer_id}) has no phone number, skipping\n'
                    )
                    skipped_count += 1
                    continue

                # Generate password
                password = generate_password()
                password_hash = make_password(password)

                # Create portal auth
                CustomerPortalAuth.objects.create(
                    customer=customer,
                    phone_number=phone_number,
                    password_hash=password_hash,
                    is_active=True
                )

                self.stdout.write(
                    f'  [OK] Created account for {customer.name}\n'
                    f'     Phone: {phone_number}\n'
                    f'     Password: {password}\n'
                )
                created_count += 1

            except Customer.DoesNotExist:
                self.stdout.write(f'  [ERROR] Customer with ID {customer_id} not found\n')
                skipped_count += 1
            except Exception as e:
                self.stdout.write(f'  [ERROR] Error processing customer {customer_id}: {e}\n')
                skipped_count += 1

        self.stdout.write('\n' + '-' * 60 + '\n')
        self.stdout.write(
            f'Summary:\n'
            f'  Created: {created_count}\n'
            f'  Already existed: {already_exists_count}\n'
            f'  Skipped: {skipped_count}\n'
            f'  Total customers processed: {len(all_customer_ids)}\n'
        )
