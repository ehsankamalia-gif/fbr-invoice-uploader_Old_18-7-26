"""Phase 4 JSON API: Staff Management (list/create staff & admin accounts,
grant/revoke access, activate/deactivate, reset password). Gated by
IsAdminRole throughout - only Admins may manage other accounts, mirroring
portal.permissions.admin_required. Ports the logic that used to live in
portal/views.py's staff_* views, which backed the (now retired)
server-rendered staff_list/staff_form/staff_permissions templates."""

import secrets

from django.contrib.auth.models import User, Permission
from django.contrib.contenttypes.models import ContentType
from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView

from .api_permissions import IsAdminRole
from .models import StaffAccess, STAFF_MODULES, UserProfile
from .permissions import get_profile
from .serializers import StaffUserSerializer


def _staff_permission_queryset():
    content_type = ContentType.objects.get_for_model(StaffAccess)
    return Permission.objects.filter(content_type=content_type)


class StaffListView(generics.ListAPIView):
    serializer_class = StaffUserSerializer
    permission_classes = [IsAdminRole]

    def get_queryset(self):
        qs = User.objects.filter(is_staff=True).order_by('-date_joined')
        for user in qs:
            get_profile(user)
        return qs


@api_view(['POST'])
@permission_classes([IsAdminRole])
def staff_create_view(request):
    username = (request.data.get('username') or '').strip()
    email = (request.data.get('email') or '').strip()
    password = (request.data.get('password') or '').strip()
    role = request.data.get('role', UserProfile.STAFF)
    if role not in (UserProfile.ADMIN, UserProfile.STAFF):
        role = UserProfile.STAFF

    if not username or not password:
        return Response({'detail': 'Username and password are required.'}, status=400)
    if len(password) < 8:
        return Response({'detail': 'Password must be at least 8 characters.'}, status=400)
    if User.objects.filter(username=username).exists():
        return Response({'detail': f'Username "{username}" is already taken.'}, status=400)

    user = User.objects.create_user(username=username, email=email, password=password)
    user.is_staff = True
    user.is_superuser = (role == UserProfile.ADMIN)
    user.save()
    UserProfile.objects.update_or_create(user=user, defaults={'role': role})

    return Response(StaffUserSerializer(user).data, status=201)


class StaffPermissionsView(APIView):
    """GET returns the account's current role + granted module codenames
    (plus the full STAFF_MODULES catalog, for rendering the checkbox list).
    PUT saves a new role and, for Staff, the selected module codenames."""

    permission_classes = [IsAdminRole]

    def get(self, request, user_id):
        target = get_object_or_404(User, id=user_id)
        profile = get_profile(target)
        content_type = ContentType.objects.get_for_model(StaffAccess)
        current_codenames = list(
            target.user_permissions.filter(content_type=content_type).values_list('codename', flat=True)
        )
        return Response({
            'user': StaffUserSerializer(target).data,
            'role': profile.role,
            'modules': STAFF_MODULES,
            'current_codenames': current_codenames,
            'is_self': target == request.user,
        })

    def put(self, request, user_id):
        target = get_object_or_404(User, id=user_id)
        profile = get_profile(target)
        new_role = request.data.get('role', UserProfile.STAFF)
        if new_role not in (UserProfile.ADMIN, UserProfile.STAFF):
            new_role = UserProfile.STAFF

        if target == request.user and new_role != UserProfile.ADMIN:
            return Response({'detail': "You can't remove your own Admin role."}, status=400)

        profile.role = new_role
        profile.save(update_fields=['role'])

        if new_role == UserProfile.ADMIN:
            target.is_superuser = True
            target.is_staff = True
            target.save()
            target.user_permissions.clear()
        else:
            target.is_superuser = False
            target.is_staff = True
            target.save()
            selected_codes = request.data.get('permissions', [])
            perms_qs = _staff_permission_queryset().filter(codename__in=selected_codes)
            target.user_permissions.set(perms_qs)

        return Response(StaffUserSerializer(target).data)


@api_view(['POST'])
@permission_classes([IsAdminRole])
def staff_toggle_active_view(request, user_id):
    target = get_object_or_404(User, id=user_id)
    if target == request.user:
        return Response({'detail': "You can't deactivate your own account."}, status=400)
    target.is_active = not target.is_active
    target.save(update_fields=['is_active'])
    return Response(StaffUserSerializer(target).data)


@api_view(['POST'])
@permission_classes([IsAdminRole])
def staff_reset_password_view(request, user_id):
    target = get_object_or_404(User, id=user_id)
    temp_password = secrets.token_urlsafe(9)
    target.set_password(temp_password)
    target.save(update_fields=['password'])
    return Response({'temp_password': temp_password})
