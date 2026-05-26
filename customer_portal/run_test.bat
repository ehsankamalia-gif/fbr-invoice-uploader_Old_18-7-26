
@echo off
cd /d c:\laragon\www\fbr-invoice-uploader\customer_portal
python -c "import os, django; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'customer_portal.settings'); django.setup(); from portal.models import CustomerPortalAuth; from django.contrib.auth.hashers import check_password, make_password; auths = CustomerPortalAuth.objects.all(); print('Auths found:', len(auths)); [print('ID:', a.id, 'Phone:', repr(a.phone_number), 'Is Active:', a.is_active, 'Check 123456789:', check_password('123456789', a.password_hash)) for a in auths]"
