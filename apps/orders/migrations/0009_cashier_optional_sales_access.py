from django.db import migrations


def restore_configured_cashier_access(apps, schema_editor):
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")
    alias = schema_editor.connection.alias
    cashier, _ = Group.objects.using(alias).get_or_create(name="CASHIER")
    permissions = Permission.objects.using(alias).filter(
        content_type__app_label="orders",
        codename__in=("view_order", "manage_order", "collect_payment"),
    )
    cashier.permissions.add(*permissions)


class Migration(migrations.Migration):
    dependencies = [("orders", "0008_order_codes_and_item_totals")]
    operations = [migrations.RunPython(restore_configured_cashier_access, migrations.RunPython.noop)]
