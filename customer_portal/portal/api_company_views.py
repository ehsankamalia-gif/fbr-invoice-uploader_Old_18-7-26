"""Company profile management from the customer portal - lets the same
install be handed to a different business without touching source code:
each company enters its own Name/Address/Phone/Email/NTN once here, and
exactly one company is "active" at a time (mirrors the FBR SANDBOX/
PRODUCTION is_active toggle in api_fbr_config_views.py). The active
company's id is what portal/managers.py's CompanyScopedManager filters
every scoped model's queryset by, so switching the active company here
changes what every other page in the portal shows."""
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .api_permissions import HasPortalPermission
from .company_service import invalidate_cache
from .db_utils import refresh_pk_after_insert
from .models import Company
from .serializers import CompanySerializer


@api_view(['GET', 'POST'])
@permission_classes([HasPortalPermission('manage_companies')])
def company_list_view(request):
    if request.method == 'POST':
        serializer = CompanySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # id is a plain IntegerField PK (mirrors the desktop's SQLAlchemy
        # schema, see db_utils.refresh_pk_after_insert), so the
        # auto-incremented id must be pulled back manually after INSERT.
        instance = Company(**serializer.validated_data, is_active=False, is_deleted=False)
        instance.save()
        refresh_pk_after_insert(instance)
        return Response(CompanySerializer(instance).data, status=201)

    companies = Company.objects.filter(is_deleted=False).order_by('name')
    return Response(CompanySerializer(companies, many=True).data)


@api_view(['PUT'])
@permission_classes([HasPortalPermission('manage_companies')])
def company_update_view(request, pk):
    try:
        company = Company.objects.get(pk=pk, is_deleted=False)
    except Company.DoesNotExist:
        return Response({'detail': 'Company not found.'}, status=404)

    serializer = CompanySerializer(company, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([HasPortalPermission('manage_companies')])
def company_activate_view(request, pk):
    try:
        company = Company.objects.get(pk=pk, is_deleted=False)
    except Company.DoesNotExist:
        return Response({'detail': 'Company not found.'}, status=404)

    Company.objects.update(is_active=False)
    company.is_active = True
    company.save(update_fields=['is_active'])
    invalidate_cache()
    return Response(CompanySerializer(company).data)
