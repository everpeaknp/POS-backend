"""Shared helpers for issuing JWT auth responses."""

from users.serializers import CustomTokenObtainPairSerializer


def build_user_payload(user):
    return {
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'phone': user.phone,
        'avatar': user.avatar.url if user.avatar else None,
        'role': user.role,
        'permissions': {
            'is_admin': user.is_admin,
            'is_manager': user.is_manager,
            'is_supervisor': user.is_supervisor,
            'is_accountant': user.is_accountant,
            'is_viewer': user.is_viewer,
            'can_approve_purchases': user.can_approve_purchases(),
            'can_manage_users': user.can_manage_users(),
            'can_view_financials': user.can_view_financials(),
            'can_edit_data': user.can_edit_data(),
            'modules': {
                'dashboard': user.has_module_access('dashboard'),
                'sales': user.has_module_access('sales'),
                'purchase': user.has_module_access('purchase'),
                'inventory': user.has_module_access('inventory'),
                'construction': user.has_module_access('construction'),
                'accounting': user.has_module_access('accounting'),
                'hardware': user.has_module_access('hardware'),
                'reports': user.has_module_access('reports'),
                'settings': user.has_module_access('settings'),
                'pos': user.has_module_access('pos'),
                'hr': user.has_module_access('hr'),
            },
        },
    }


def build_tenant_payload(user):
    tenant = user.get_tenant()
    if not tenant:
        return None
    return {
        'id': tenant.id,
        'name': tenant.name,
        'slug': tenant.slug,
        'workspace_name': tenant.workspace_name,
        'email': tenant.email,
        'address': tenant.address,
        'business_type': tenant.business_type,
        'plan_type': tenant.plan_type,
        'active_modules': tenant.active_modules,
    }


def issue_tokens_for_user(user, request=None):
    refresh = CustomTokenObtainPairSerializer.get_token(user)
    data = {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
        'user': build_user_payload(user),
        'tenant': build_tenant_payload(user),
    }
    if request:
        from users.session_utils import record_user_session
        session = record_user_session(user, request, data['refresh'])
        data['session_id'] = str(session.id)
    return data
