from functools import wraps

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import render

from .models import UserProfile


def get_profile(user):
    """Return the user's role profile, creating a default (Staff) one if missing.

    Self-healing rather than migration-backfilled, since accounts can also be
    created outside this app's flow (e.g. `manage.py createsuperuser`).
    """
    profile, created = UserProfile.objects.get_or_create(user=user)
    if created and user.is_superuser:
        profile.role = UserProfile.ADMIN
        profile.save(update_fields=['role'])
    return profile


def staff_required(perm_code=None):
    """Gate a custom-admin view to logged-in staff/admin accounts.

    Admins (Django superusers) always pass. Staff accounts must hold the
    named `portal.<perm_code>` permission, which only an Admin can grant
    (via the Staff Management pages).
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            user = request.user
            if not (user.is_authenticated and user.is_active and user.is_staff):
                return redirect_to_login(request.get_full_path(), login_url='/custom-admin/login/')
            if user.is_superuser:
                return view_func(request, *args, **kwargs)
            if perm_code and not user.has_perm(f'portal.{perm_code}'):
                messages.error(request, "You don't have permission to access that page.")
                return render(request, 'portal/custom_admin/no_access.html', status=403)
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator
