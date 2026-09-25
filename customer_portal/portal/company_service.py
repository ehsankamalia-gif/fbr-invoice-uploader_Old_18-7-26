"""Active-company resolution for the Django portal - the equivalent of the
desktop app's settings_service.get_active_company_id(). A single global
"active" row (companies.is_active), not a per-user/per-session concept -
matches how switching the FBR SANDBOX/PRODUCTION environment already works
in this codebase. portal/managers.py's CompanyScopedManager calls
get_active_company_id() to transparently filter every scoped model's
queryset to just that company's rows.
"""
import time
from typing import Optional

_cache_id: Optional[int] = None
_cache_loaded_at: float = 0.0
_CACHE_TTL_SECONDS = 5


def get_active_company_id() -> Optional[int]:
    global _cache_id, _cache_loaded_at
    if _cache_id is not None and (time.time() - _cache_loaded_at) < _CACHE_TTL_SECONDS:
        return _cache_id

    from .models import Company
    # .using(None) isn't needed - Company's manager is never scoped by
    # itself (see managers.py docstring), so this is a plain, unfiltered read.
    company = Company.objects.filter(is_active=True, is_deleted=False).order_by('id').first()
    company_id = company.id if company else None
    _cache_id = company_id
    _cache_loaded_at = time.time()
    return company_id


def invalidate_cache() -> None:
    global _cache_id, _cache_loaded_at
    _cache_id = None
    _cache_loaded_at = 0.0


def get_active_company() -> Optional[dict]:
    from .models import Company
    company = Company.objects.filter(is_active=True, is_deleted=False).order_by('id').first()
    if not company:
        return None
    return {
        'id': company.id, 'name': company.name, 'ntn': company.ntn,
        'cnic': company.cnic, 'address': company.address,
        'phone': company.phone, 'email': company.email,
    }
