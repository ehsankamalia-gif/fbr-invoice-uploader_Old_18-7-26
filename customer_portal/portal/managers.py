"""Global multi-company query filtering for the Django side - the
equivalent of app/db/company_scope.py on the desktop app. Every model that
should only ever show the active company's rows gets
`objects = CompanyScopedManager()` (see portal/models.py), which is a
single choke point instead of editing ~97+ existing `.objects` call sites
individually across the admin API views.

Company itself, FBRConfiguration, and CustomerPortalAuth deliberately keep
Django's plain default manager: Company can't scope itself (chicken-and-
egg - resolving the active company would recurse into itself), and neither
fbr_configurations nor customer_portal_auth carry a company_id column at
the DB level (matching the desktop app's app/db/company_scope.py, which
excludes the same three for the same reasons).
"""
from django.db import models

from .company_service import get_active_company_id


class CompanyScopedManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(company_id=get_active_company_id())
