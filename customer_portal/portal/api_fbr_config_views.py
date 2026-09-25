"""FBR configuration management from the customer portal - mirrors the
desktop app's Settings screen (app/services/settings_service.py's
save_environment/set_active_environment) closely, since this is the exact
same `fbr_configurations` row both apps read from. Editing it here changes
what BOTH apps use for their next FBR submission - gated by the single
manage_fbr_config permission, grantable only by an Admin."""
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .api_permissions import HasPortalPermission
from .db_utils import refresh_pk_after_insert
from .models import FBRConfiguration
from .serializers import FBRConfigurationSerializer

VALID_ENVIRONMENTS = ('SANDBOX', 'PRODUCTION')

_DEFAULTS = {
    'SANDBOX': 'https://esp.fbr.gov.pk:8243/PT/v1',
    'PRODUCTION': 'https://gw.fbr.gov.pk/imsp/v1/api/Live',
}


def _get_config_row(environment):
    """The desktop app's own startup code (_initialize_defaults) can race
    when two instances launch at once and create duplicate SANDBOX/
    PRODUCTION rows with blank values (environment isn't actually enforced
    unique at the DB level for this managed=False table). Rather than ever
    touching/deleting those duplicates ourselves, always deterministically
    resolve to the one row that matters: the active one if any, else the
    one that actually has real values, else the oldest row."""
    qs = FBRConfiguration.objects.filter(environment=environment)
    return (
        qs.filter(is_active=True).order_by('id').first()
        or qs.exclude(pos_id='').exclude(pos_id__isnull=True).order_by('id').first()
        or qs.order_by('id').first()
    )


@api_view(['GET'])
@permission_classes([HasPortalPermission('manage_fbr_config')])
def fbr_config_list_view(request):
    result = {}
    active = None
    for env in VALID_ENVIRONMENTS:
        config = _get_config_row(env)
        result[env.lower()] = FBRConfigurationSerializer(config).data if config else None
        if config and config.is_active:
            active = env
    return Response({'sandbox': result['sandbox'], 'production': result['production'], 'active': active})


@api_view(['PUT'])
@permission_classes([HasPortalPermission('manage_fbr_config')])
def fbr_config_update_view(request, environment):
    environment = (environment or '').upper()
    if environment not in VALID_ENVIRONMENTS:
        return Response({'detail': 'Environment must be SANDBOX or PRODUCTION.'}, status=400)

    for numeric_field in ('tax_rate', 'discount', 'pos_fee'):
        if numeric_field in request.data:
            try:
                float(request.data[numeric_field])
            except (TypeError, ValueError):
                return Response({numeric_field: ['Must be a number.']}, status=400)

    config = _get_config_row(environment)
    if not config:
        # New row - id is a plain IntegerField PK (mirrors the desktop's
        # SQLAlchemy schema, see db_utils.refresh_pk_after_insert), so the
        # auto-incremented id must be pulled back manually after INSERT.
        config = FBRConfiguration(environment=environment, api_base_url=_DEFAULTS[environment])
        config.save()
        refresh_pk_after_insert(config)
    serializer = FBRConfigurationSerializer(config, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([HasPortalPermission('manage_fbr_config')])
def fbr_config_activate_view(request, environment):
    environment = (environment or '').upper()
    if environment not in VALID_ENVIRONMENTS:
        return Response({'detail': 'Environment must be SANDBOX or PRODUCTION.'}, status=400)

    config = _get_config_row(environment)
    if not config:
        return Response({'detail': f'No {environment} configuration exists yet - save one first.'}, status=400)

    FBRConfiguration.objects.update(is_active=False)
    config.is_active = True
    config.save(update_fields=['is_active'])
    return Response(FBRConfigurationSerializer(config).data)
