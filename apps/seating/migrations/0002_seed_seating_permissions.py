from django.db import migrations


def seed_permissions(apps, schema_editor):
    alias = schema_editor.connection.alias
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")
    permissions = {}
    for model, codenames in (
        ("area", ("view_area",)),
        ("diningtable", ("view_diningtable", "manage_seating")),
        ("seatingactivitylog", ("view_seatingactivitylog",)),
    ):
        content_type, _ = ContentType.objects.using(alias).get_or_create(app_label="seating", model=model)
        for codename in codenames:
            permissions[codename], _ = Permission.objects.using(alias).get_or_create(
                content_type=content_type, codename=codename, defaults={"name": codename.replace("_", " ")},
            )
    for code in ("MANAGER", "WAITER", "CASHIER"):
        group, _ = Group.objects.using(alias).get_or_create(name=code)
        if code == "MANAGER":
            group.permissions.add(*permissions.values())
        else:
            group.permissions.add(permissions["view_area"], permissions["view_diningtable"])


class Migration(migrations.Migration):
    dependencies = [("seating", "0001_initial"), ("employees", "0009_rename_manager_position")]
    operations = [migrations.RunPython(seed_permissions, migrations.RunPython.noop)]
