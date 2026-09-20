from rest_framework.permissions import BasePermission

from .api_auth import CustomerPrincipal


class IsCustomer(BasePermission):
    """Mirrors portal.views.customer_login_required."""

    def has_permission(self, request, view):
        return isinstance(request.user, CustomerPrincipal)


class IsStaffMember(BasePermission):
    """Any logged-in staff or admin account, regardless of specific permissions
    (e.g. for logout, where no particular portal.* permission should matter)."""

    def has_permission(self, request, view):
        user = request.user
        return bool(getattr(user, 'is_authenticated', False) and user.is_active and user.is_staff)


class IsAdminRole(BasePermission):
    """Mirrors portal.permissions.admin_required (superuser-only)."""

    def has_permission(self, request, view):
        user = request.user
        return bool(
            getattr(user, 'is_authenticated', False)
            and user.is_active
            and user.is_staff
            and user.is_superuser
        )


def HasPortalPermission(perm_code):
    """Factory mirroring portal.permissions.staff_required(perm_code):
    superusers bypass, staff must hold the named portal.<perm_code> permission."""

    class _HasPortalPermission(BasePermission):
        def has_permission(self, request, view):
            user = request.user
            if not (getattr(user, 'is_authenticated', False) and user.is_active and user.is_staff):
                return False
            if user.is_superuser:
                return True
            return user.has_perm(f'portal.{perm_code}')

    _HasPortalPermission.__name__ = f'HasPortalPermission_{perm_code}'
    return _HasPortalPermission
