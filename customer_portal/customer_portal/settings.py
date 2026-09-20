
import os
import sys
import urllib.parse
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

sys.path.append(str(BASE_DIR.parent))

load_dotenv(os.path.join(BASE_DIR, '.env'))

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'django-insecure-change-this-in-production-!@#$%^&*()')

DEBUG = os.getenv('DJANGO_DEBUG', 'True') == 'True'

ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'portal',
]

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        'portal.api_auth.CustomerSessionAuthentication',
    ],
    # Deliberately empty: every view sets its own permission_classes explicitly,
    # mirroring how the remaining server-rendered Django views (get_customer_data,
    # credit_customers_view, the CSV exports) already wrap themselves in
    # @staff_required(...) today.
    'DEFAULT_PERMISSION_CLASSES': [],
}

# Bumped on each frontend build; used as a cache-busting query param on the
# SPA's built assets (see templates/spa/shell.html).
SPA_BUILD_VERSION = '2'

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'customer_portal.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'portal.context_processors.feature_flags',
            ],
        },
    },
]

WSGI_APPLICATION = 'customer_portal.wsgi.application'


def get_database_url():
    """Get database URL from environment, supporting both MySQL and SQLite like the main app.
    Defaults to SQLite at project root (fbr_invoices.db) which matches desktop app.
    """
    server = os.getenv("DB_SERVER")
    if server:
        user = os.getenv("DB_USER", "root")
        password = os.getenv("DB_PASSWORD", "")
        port = os.getenv("DB_PORT", "3306")
        name = os.getenv("DB_NAME", "fbr_invoice_uploader")
        encoded_password = urllib.parse.quote_plus(password)
        return f"mysql+pymysql://{user}:{encoded_password}@{server}:{port}/{name}"
    
    # Use the SQLite database at project root (matches desktop app's database)
    parent_db = BASE_DIR.parent / "fbr_invoices.db"
    if parent_db.exists():
        print(f"Using SQLite database at: {parent_db}")
        return f"sqlite:///{parent_db}"
    
    return f"sqlite:///{BASE_DIR.parent / 'fbr_invoice_uploader.db'}"


DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

db_url = get_database_url()
if 'mysql' in db_url:
    DATABASES['default'] = {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': os.getenv("DB_NAME", "fbr_invoice_uploader"),
        'USER': os.getenv("DB_USER", "root"),
        'PASSWORD': os.getenv("DB_PASSWORD", ""),
        'HOST': os.getenv("DB_SERVER", "localhost"),
        'PORT': os.getenv("DB_PORT", "3306"),
        'OPTIONS': {
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
            'charset': 'utf8mb4',
        },
    }
else:
    sqlite_path = db_url.replace('sqlite:///', '')
    DATABASES['default'] = {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': sqlite_path,
        'OPTIONS': {
            'timeout': 20,
            'check_same_thread': False,
        },
    }

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Karachi'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = '/custom-admin/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/custom-admin/login/'

# Only disable migration checks for unmanaged models, but keep migrations enabled for managed ones
# MIGRATION_MODULES = {
#     'portal': None,
# }
