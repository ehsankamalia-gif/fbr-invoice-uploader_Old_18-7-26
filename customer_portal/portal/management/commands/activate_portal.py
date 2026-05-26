
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.hashers import make_password
from portal.models import Customer


class Command(BaseCommand):
    help = 'Activate portal access for a customer'

    def add_arguments(self, parser):
        parser.add_argument('customer_id', type=int, help='Customer ID')
        parser.add_argument('username', type=str, help='Username for portal login')
        parser.add_argument('password', type=str, help='Password for portal login')

    def handle(self, *args, **options):
        customer_id = options['customer_id']
        username = options['username']
        password = options['password']
        
        try:
            customer = Customer.objects.get(id=customer_id)
        except Customer.DoesNotExist:
            raise CommandError(f'Customer with ID {customer_id} does not exist')
        
        if Customer.objects.filter(username=username).exclude(id=customer_id).exists():
            raise CommandError(f'Username "{username}" is already taken')
        
        customer.username = username
        customer.password_hash = make_password(password)
        customer.is_portal_active = True
        customer.save()
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully activated portal access for {customer.name}!\n'
                f'Username: {username}\n'
                f'Customer ID: {customer_id}'
            )
        )
