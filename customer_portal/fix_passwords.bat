
@echo off
cd /d c:\laragon\www\fbr-invoice-uploader\customer_portal
python manage.py shell < fix_portal_passwords.py
