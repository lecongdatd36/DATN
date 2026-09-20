"""Seed customer permissions explicitly, including on a fresh database."""
from django.db import migrations


def seed_permissions(apps, schema_editor):
    alias = schema_editor.connection.alias
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")
    permissions = {}
    for model, actions in (("customer", ("view", "add", "change", "delete")), ("customeractivitylog", ("view",))):
        content_type, _ = ContentType.objects.using(alias).get_or_create(app_label="customers", model=model)
        for action in actions:
            codename = f"{action}_{model}"
            permission, _ = Permission.objects.using(alias).get_or_create(
                content_type=content_type, codename=codename,
                defaults={"name": f"Can {action} {model}"},
            )
            permissions[codename] = permission
    for code in ("MANAGER", "WAITER", "CASHIER", "KITCHEN", "INVENTORY"):
        group, _ = Group.objects.using(alias).get_or_create(name=code)
        if code == "MANAGER":
            group.permissions.add(*permissions.values())
        elif code in ("WAITER", "CASHIER"):
            group.permissions.add(*(permissions[key] for key in ("view_customer", "add_customer", "change_customer")))


class Migration(migrations.Migration):
    dependencies = [
        ("customers", "0001_initial"),
        ("employees", "0009_rename_manager_position"),
    ]
    operations = [migrations.RunPython(seed_permissions, migrations.RunPython.noop)]
