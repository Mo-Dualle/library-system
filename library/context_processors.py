"""Template context mirroring staff permission checks (includes legacy full-staff rule)."""

from .roles import (
    PERM_ACCESS_STAFF_DASHBOARD,
    PERM_MANAGE_CATALOG,
    PERM_MANAGE_CIRCULATION,
    PERM_MANAGE_FINES_STAFF,
    PERM_MANAGE_MEMBERS,
    PERM_MANAGE_STAFF_ACCOUNTS,
    is_portal_staff,
    user_has_staff_perm,
)


def staff_access(request):
    """Expose booleans for navbar and admin UI; None when not applicable."""
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or not is_portal_staff(user):
        return {"staff_access": None}
    access = {
        "staff_access": {
            "portal": user_has_staff_perm(user, PERM_ACCESS_STAFF_DASHBOARD),
            "catalog": user_has_staff_perm(user, PERM_MANAGE_CATALOG),
            "circulation": user_has_staff_perm(user, PERM_MANAGE_CIRCULATION),
            "fines": user_has_staff_perm(user, PERM_MANAGE_FINES_STAFF),
            "members": user_has_staff_perm(user, PERM_MANAGE_MEMBERS),
            "staff_accounts": user_has_staff_perm(user, PERM_MANAGE_STAFF_ACCOUNTS),
        }
    }
    return access
