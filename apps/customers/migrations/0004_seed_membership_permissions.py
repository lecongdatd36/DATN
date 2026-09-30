from django.db import migrations


def seed_permissions(apps, schema_editor):
    alias = schema_editor.connection.alias
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")
    content_type, _ = ContentType.objects.using(alias).get_or_create(app_label="customers", model="membershiptier")
    permissions = []
    for action in ("view", "add", "change", "delete"):
        permission, _ = Permission.objects.using(alias).get_or_create(
            content_type=content_type,
            codename=f"{action}_membershiptier",
            defaults={"name": f"Can {action} membership tier"},
        )
        permissions.append(permission)
    manager, _ = Group.objects.using(alias).get_or_create(name="MANAGER")
    manager.permissions.add(*permissions)


class Migration(migrations.Migration):
    dependencies = [("customers", "0003_membership"), ("employees", "0009_rename_manager_position")]
    operations = [migrations.RunPython(seed_permissions, migrations.RunPython.noop)]
