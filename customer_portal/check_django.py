import sys
sys.path.insert(0, 'c:\\laragon\\www\\fbr-invoice-uploader_Old_18-7-26\\customer_portal')
import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'customer_portal.settings'
import django
django.setup()
print('Django setup OK')
