"""
Staff role helpers: Librarian, Finance Officer, User Manager.

Legacy behaviour: is_staff users who are not in any of the three role groups
(or Django superusers) keep full access to all staff features.
"""

from __future__ import annotations

from functools import wraps

from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied

# Group names — must match migration `library/migrations/0003_*.py`
GROUP_LIBRARIAN = "Librarian"
GROUP_FINANCE_OFFICER = "Finance Officer"
GROUP_USER_MANAGER = "User Manager"

STAFF_ROLE_GROUP_NAMES = frozenset({
    GROUP_LIBRARIAN,
    GROUP_FINANCE_OFFICER,
    GROUP_USER_MANAGER,
})

def is_portal_staff(user) -> bool:
    """
    True if this account may use the in-app staff panel (URLs under admin-panel).

    Either the Django ``is_staff`` flag is set, or the user belongs to one of the
    three library role groups. The latter fixes accounts that were only given groups
    in Django admin without ``is_staff=True`` (they would otherwise behave as members).
    """
    if not user.is_authenticated or not user.is_active:
        is_portal = False
    elif user.is_staff:
        is_portal = True
    else:
        is_portal = user.groups.filter(name__in=STAFF_ROLE_GROUP_NAMES).exists()
    return is_portal


# Custom permission codenames on library.Account (full names for has_perm)
PERM_ACCESS_STAFF_DASHBOARD = "library.access_staff_dashboard"
PERM_MANAGE_CATALOG = "library.manage_catalog"
PERM_MANAGE_CIRCULATION = "library.manage_circulation"
PERM_MANAGE_FINES_STAFF = "library.manage_fines_staff"
PERM_MANAGE_MEMBERS = "library.manage_members"
PERM_MANAGE_STAFF_ACCOUNTS = "library.manage_staff_accounts"


def user_has_assigned_staff_role(user) -> bool:
    """True if the user belongs to at least one of the three named role groups."""
    if not user.is_authenticated:
        return False
    return user.groups.filter(name__in=STAFF_ROLE_GROUP_NAMES).exists()


def is_legacy_full_staff(user) -> bool:
    """
    Staff with no assigned role group keeps the old behaviour (all staff areas).

    Superusers are always treated as full staff for the in-app admin panel.
    """
    if not user.is_authenticated or not user.is_staff:
        return False
    if user.is_superuser:
        return True
    return not user_has_assigned_staff_role(user)


def user_has_staff_perm(user, perm: str) -> bool:
    """
    Check a staff-only permission. Legacy full staff and superusers pass all checks.

    `perm` must be the full string, e.g. ``library.manage_catalog``.
    """
    if not user.is_authenticated or not user.is_active or not is_portal_staff(user):
        result = False
        reason = "not_portal_or_inactive"
    elif is_legacy_full_staff(user):
        result = True
        reason = "legacy_full_staff"
    else:
        result = user.has_perm(perm)
        reason = "django_perm_check"
    return result


# Staff home template keys (see ``staff_dashboard_kind``).
STAFF_DASHBOARD_FULL = "full"
STAFF_DASHBOARD_FINANCE = "finance"
STAFF_DASHBOARD_LIBRARIAN = "librarian"
STAFF_DASHBOARD_USER_MANAGER = "user_manager"


def staff_dashboard_kind(user) -> str:
    """
    Which staff home page to show after login.

    Legacy full staff and anyone with more than one functional area see the
    combined ``full`` dashboard. Single-area roles get a dedicated home so they
    never land on the member borrowing dashboard.
    """
    if not is_portal_staff(user):
        return STAFF_DASHBOARD_FULL
    if is_legacy_full_staff(user):
        return STAFF_DASHBOARD_FULL

    lib = user_has_staff_perm(user, PERM_MANAGE_CATALOG) or user_has_staff_perm(
        user, PERM_MANAGE_CIRCULATION
    )
    fin = user_has_staff_perm(user, PERM_MANAGE_FINES_STAFF)
    um = user_has_staff_perm(user, PERM_MANAGE_MEMBERS) or user_has_staff_perm(
        user, PERM_MANAGE_STAFF_ACCOUNTS
    )

    areas = [key for key, ok in (("lib", lib), ("fin", fin), ("um", um)) if ok]
    if len(areas) != 1:
        kind = STAFF_DASHBOARD_FULL
    elif areas[0] == "fin":
        kind = STAFF_DASHBOARD_FINANCE
    elif areas[0] == "lib":
        kind = STAFF_DASHBOARD_LIBRARIAN
    else:
        kind = STAFF_DASHBOARD_USER_MANAGER
    return kind


def require_staff_permissions(*perms: str, match_any: bool = True):
    """
    Decorator: user must be staff and satisfy permission checks (OR by default).

    Example::

        @require_staff_permissions(PERM_MANAGE_CATALOG)
        def admin_book_list_view(request): ...
    """

    if not perms:
        raise ValueError("require_staff_permissions needs at least one permission string")

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated or not is_portal_staff(request.user):
                raise PermissionDenied
            checks = [user_has_staff_perm(request.user, p) for p in perms]
            ok = any(checks) if match_any else all(checks)
            if not ok:
                raise PermissionDenied
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def ensure_staff_role_groups_exist() -> None:
    """
    Idempotent safety net for dev DBs created before the data migration.
    """
    for name in STAFF_ROLE_GROUP_NAMES:
        Group.objects.get_or_create(name=name)


def set_staff_role_groups(
    user,
    *,
    full_access: bool,
    librarian: bool = False,
    finance_officer: bool = False,
    user_manager: bool = False,
) -> None:
    """
    Replace role-group membership for a staff account.

    ``full_access=True`` clears all three role groups (legacy full staff behaviour).
    Otherwise adds the selected groups (caller must ensure at least one flag).
    """
    ensure_staff_role_groups_exist()
    role_groups = list(Group.objects.filter(name__in=STAFF_ROLE_GROUP_NAMES))
    if role_groups:
        user.groups.remove(*role_groups)
    if full_access:
        return
    to_add = []
    if librarian:
        to_add.append(Group.objects.get(name=GROUP_LIBRARIAN))
    if finance_officer:
        to_add.append(Group.objects.get(name=GROUP_FINANCE_OFFICER))
    if user_manager:
        to_add.append(Group.objects.get(name=GROUP_USER_MANAGER))
    if to_add:
        user.groups.add(*to_add)

    # Anyone with a library role must log in as staff, not as a borrowing member.
    if user_has_assigned_staff_role(user):
        from .models import Account

        Account.objects.filter(pk=user.pk).update(is_staff=True, is_member=False)
        user.is_staff = True
        user.is_member = False
