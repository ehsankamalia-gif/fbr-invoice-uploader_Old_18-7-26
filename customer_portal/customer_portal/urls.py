"""customer_portal URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, re_path, include
from django.views.generic import RedirectView

from portal.spa_views import spa_shell_view

urlpatterns = [
    # The raw Django admin is kept only as a hidden, superuser-only fallback.
    # Everyday staff/admin work happens in the custom BikeZone admin UI below.
    path('django-admin/', admin.site.urls),
    path('admin/', RedirectView.as_view(url='/custom-admin/', permanent=False)),
    path('admin/<path:subpath>', RedirectView.as_view(url='/custom-admin/', permanent=False)),

    path('api/v1/', include('portal.api_urls')),

    # A handful of real (non-SPA) Django views still live under fixed paths -
    # the credit-customers redirect/report, staff logout, CSV exports (see
    # portal/urls.py). Included before the SPA catch-alls below so those
    # specific paths keep resolving to their real views instead of falling
    # through to the Vue shell.
    path('', include('portal.urls')),

    # --- Vue 3 SPA (all 5 rewrite phases) ---
    # Every page - customer portal and admin ("Manage Data", reports, Staff
    # Management) - is now a Vue route. Both branches render the exact same
    # shell; Vue Router (history mode) reads the URL client-side and mounts
    # the right page. A hard refresh/bookmark on any nested URL still works
    # since Django just re-serves the same shell and Vue Router takes it
    # from there. The admin branch gets its own catch-all (rather than one
    # global '.*') only so it stays clearly separate from the '/admin/'
    # raw-Django-admin redirect above.
    re_path(r'^custom-admin/.*$', spa_shell_view),
    re_path(r'^.*$', spa_shell_view),
]
