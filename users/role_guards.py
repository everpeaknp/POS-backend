"""Role assignment guards for invites and user management."""
from rest_framework.exceptions import ValidationError

from users.dynamic_permissions import has_permission

VALID_ROLES = frozenset({'admin', 'manager', 'supervisor', 'accountant', 'cashier', 'viewer'})


def assert_user_can_assign_role(user, role: str) -> str:
    normalized = (role or 'viewer').strip().lower()
    if normalized not in VALID_ROLES:
        raise ValidationError({'role': 'Invalid role.'})

    if normalized == 'admin' and not has_permission(user, 'settings', 'edit'):
        raise ValidationError({'role': 'Only settings administrators can assign the Admin role.'})

    if not (
        has_permission(user, 'settings', 'edit')
        or has_permission(user, 'hr', 'invite')
        or has_permission(user, 'hr', 'assign')
    ):
        raise ValidationError({'role': 'You do not have permission to assign roles.'})

    return normalized
