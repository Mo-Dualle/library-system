# Staff RBAC: custom Account permissions + auth groups (Librarian, Finance Officer, User Manager).

from django.db import migrations

GROUP_LIBRARIAN = "Librarian"
GROUP_FINANCE_OFFICER = "Finance Officer"
GROUP_USER_MANAGER = "User Manager"

GROUP_PERMISSIONS = {
    GROUP_LIBRARIAN: (
        "access_staff_dashboard",
        "manage_catalog",
        "manage_circulation",
    ),
    GROUP_FINANCE_OFFICER: (
        "access_staff_dashboard",
        "manage_fines_staff",
    ),
    GROUP_USER_MANAGER: (
        "access_staff_dashboard",
        "manage_members",
        "manage_staff_accounts",
    ),
}


def forwards(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")

    try:
        ct = ContentType.objects.get(app_label="library", model="account")
    except ContentType.DoesNotExist:
        return

    perms_by_codename = {
        p.codename: p
        for p in Permission.objects.filter(content_type=ct)
    }

    for group_name, codenames in GROUP_PERMISSIONS.items():
        group, _ = Group.objects.get_or_create(name=group_name)
        wanted = [perms_by_codename[c] for c in codenames if c in perms_by_codename]
        group.permissions.set(wanted)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("library", "0002_alter_account_gender"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="account",
            options={
                "db_table": "account",
                "permissions": [
                    ("access_staff_dashboard", "Can access the staff dashboard"),
                    ("manage_catalog", "Can manage books, authors, and categories"),
                    ("manage_circulation", "Can manage loans and reservations"),
                    ("manage_fines_staff", "Can view and manage fines (staff)"),
                    ("manage_members", "Can manage library members and accounts"),
                    ("manage_staff_accounts", "Can create staff accounts and assign roles"),
                ],
            },
        ),
        migrations.RunPython(forwards, noop_reverse),
    ]
