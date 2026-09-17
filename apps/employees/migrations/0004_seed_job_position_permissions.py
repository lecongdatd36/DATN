from django.db import migrations


POSITION_CODES = ("MANAGER", "WAITER", "CASHIER", "KITCHEN", "INVENTORY")


def seed_groups_and_permissions(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")
    EmployeeProfile = apps.get_model("employees", "EmployeeProfile")
    User = apps.get_model("accounts", "User")

    permissions = Permission.objects.filter(
        content_type__app_label__in=("accounts", "employees"),
    )
    for code in POSITION_CODES:
        group, _ = Group.objects.get_or_create(name=code)
        if code == "MANAGER":
            group.permissions.set(permissions)
        elif code == "KITCHEN":
            group.permissions.set(permissions.filter(content_type__model__in=("employeeprofile", "employeeactivitylog")))
        elif code == "INVENTORY":
            group.permissions.set(permissions.filter(content_type__model__in=("employeeprofile", "employeeactivitylog")))
        else:
            group.permissions.set(permissions.filter(content_type__model="employeeprofile"))

    manager_group = Group.objects.filter(name="MANAGER").first()
    if manager_group:
        manager_ids = EmployeeProfile.objects.filter(job_position__code="MANAGER").values_list("user_id", flat=True)
        User.objects.filter(pk__in=manager_ids).update(is_staff=True)


def remove_seeded_permissions(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    for code in POSITION_CODES:
        group = Group.objects.filter(name=code).first()
        if group:
            group.permissions.clear()


class Migration(migrations.Migration):
    dependencies = [
        ("employees", "0003_jobposition_and_more"),
        ("accounts", "0002_remove_user_accounts_user_role_valid_and_more"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [migrations.RunPython(seed_groups_and_permissions, remove_seeded_permissions)]
