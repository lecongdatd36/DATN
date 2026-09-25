from django.db import migrations


def seed_permissions(apps, schema_editor):
    alias = schema_editor.connection.alias
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")
    permissions = {}
    for model, names in (
        ("order", ("view_order", "manage_order", "work_kitchen", "cancel_prepared_item")),
        ("orderactivitylog", ("view_orderactivitylog",)),
    ):
        content_type, _ = ContentType.objects.using(alias).get_or_create(app_label="orders", model=model)
        for name in names:
            permissions[name], _ = Permission.objects.using(alias).get_or_create(
                content_type=content_type, codename=name, defaults={"name": name.replace("_", " ")})
    for code in ("MANAGER", "WAITER", "CASHIER", "KITCHEN"):
        group, _ = Group.objects.using(alias).get_or_create(name=code)
        if code == "MANAGER":
            group.permissions.add(*permissions.values())
        elif code == "KITCHEN":
            group.permissions.add(permissions["work_kitchen"])
        else:
            group.permissions.add(permissions["view_order"], permissions["manage_order"])


class Migration(migrations.Migration):
    dependencies = [("orders", "0001_initial"), ("employees", "0009_rename_manager_position")]
    operations = [migrations.RunPython(seed_permissions, migrations.RunPython.noop)]
