
#!/usr/bin/env python
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.hashers import make_password
from portal.models import Customer, CustomerPortalAuth


class Command(BaseCommand):
    help = 'Activate a customer for portal login using phone number'

    def add_arguments(self, parser):
        parser.add_argument('customer_id', type=int, help='Customer ID to activate')
        parser.add_argument('password', type=str, help='Password for the customer')

    def handle(self, *args, **options):
        customer_id = options['customer_id']
        password = options['password']

        try:
            customer = Customer.objects.get(id=customer_id)
            
            if not customer.phone:
                self.stdout.write(self.style.ERROR(
                    f'Customer {customer_id} has no phone number! Please add a phone number first.'
                ))
                return

            auth, created = CustomerPortalAuth.objects.get_or_create(
                customer=customer,
                defaults={
                    'phone_number': customer.phone,
                    'password_hash': make_password(password),
                    'is_active': True
                }
            )
            
            if not created:
                auth.phone_number = customer.phone
                auth.password_hash = make_password(password)
                auth.is_active = True
                auth.save()

            self.stdout.write(self.style.SUCCESS(
                f'Successfully activated customer {customer_id} ({customer.name})!'
            ))
            self.stdout.write(self.style.SUCCESS(
                f'Login with phone number: {customer.phone}'
            ))
            self.stdout.write(self.style.SUCCESS(
                f'Password: {password}'
            ))

        except Customer.DoesNotExist:
            raise CommandError(f'Customer with ID {customer_id} does not exist!')
