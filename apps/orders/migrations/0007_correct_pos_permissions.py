from django.db import migrations


def correct_pos_permissions(apps, schema_editor):
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")
    alias = schema_editor.connection.alias
    permissions = {p.codename: p for p in Permission.objects.using(alias).filter(content_type__app_label="orders")}
    cashier, _ = Group.objects.using(alias).get_or_create(name="CASHIER")
    if "manage_order" in permissions:
        cashier.permissions.remove(permissions["manage_order"])
    cashier.permissions.add(*(permissions[name] for name in ("view_order", "collect_payment") if name in permissions))


class Migration(migrations.Migration):
    dependencies = [("orders", "0006_integrated_operations")]
    operations = [migrations.RunPython(correct_pos_permissions, migrations.RunPython.noop)]
