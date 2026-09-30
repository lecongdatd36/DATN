from django.db import migrations


def seed_permission(apps, schema_editor):
    alias = schema_editor.connection.alias
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")
    content_type, _ = ContentType.objects.using(alias).get_or_create(app_label="orders", model="invoice")
    permission, _ = Permission.objects.using(alias).get_or_create(
        content_type=content_type, codename="view_invoice", defaults={"name": "Can view invoice"}
    )
    manager, _ = Group.objects.using(alias).get_or_create(name="MANAGER")
    manager.permissions.add(permission)


class Migration(migrations.Migration):
    dependencies = [("orders", "0009_cashier_optional_sales_access"), ("employees", "0009_rename_manager_position")]
    operations = [migrations.RunPython(seed_permission, migrations.RunPython.noop)]
