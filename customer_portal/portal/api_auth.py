from rest_framework.authentication import SessionAuthentication

from .models import Customer


class CustomerPrincipal:
    """Duck-typed stand-in for request.user for the customer auth system,
    which has no django.contrib.auth.User at all - just
    request.session['customer_id'] (see portal.forms.LoginForm)."""

    is_authenticated = True
    is_anonymous = False
    is_active = True
    is_staff = False
    is_superuser = False

    def __init__(self, customer):
        self.customer = customer

    def __str__(self):
        return self.customer.name


class CustomerSessionAuthentication(SessionAuthentication):
    """Reads request.session['customer_id'] directly instead of assuming a
    real auth.User. Explicitly calls enforce_csrf() - DRF's APIView csrf-exempts
    every request by default, and only re-enables the check via whichever
    authenticator actually authenticated the request, so skipping this call
    would silently leave customer-authenticated POSTs unprotected."""

    def authenticate(self, request):
        customer_id = request.session.get('customer_id')
        if not customer_id:
            return None
        try:
            customer = Customer.objects.get(id=customer_id, is_deleted=False)
        except Customer.DoesNotExist:
            return None
        self.enforce_csrf(request)
        return (CustomerPrincipal(customer), None)
