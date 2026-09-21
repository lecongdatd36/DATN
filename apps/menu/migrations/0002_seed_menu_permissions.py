from django.db import migrations


def seed_permissions(apps, schema_editor):
    alias = schema_editor.connection.alias
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")
    permissions = {}
    for model, codenames in (
        ("category", ("view_category",)),
        ("unit", ("view_unit",)),
        ("dish", ("view_dish", "manage_menu", "change_availability")),
        ("menuactivitylog", ("view_menuactivitylog",)),
    ):
        content_type, _ = ContentType.objects.using(alias).get_or_create(app_label="menu", model=model)
        for codename in codenames:
            permissions[codename], _ = Permission.objects.using(alias).get_or_create(
                content_type=content_type, codename=codename, defaults={"name": codename.replace("_", " ")},
            )
    for code in ("MANAGER", "WAITER", "CASHIER", "KITCHEN"):
        group, _ = Group.objects.using(alias).get_or_create(name=code)
        if code == "MANAGER":
            group.permissions.add(*permissions.values())
        else:
            group.permissions.add(permissions["view_dish"])
            if code == "KITCHEN":
                group.permissions.add(permissions["change_availability"])


class Migration(migrations.Migration):
    dependencies = [("menu", "0001_initial"), ("employees", "0009_rename_manager_position")]
    operations = [migrations.RunPython(seed_permissions, migrations.RunPython.noop)]
