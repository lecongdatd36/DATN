from django.db import migrations, models
import django.utils.timezone


def backfill_totals(apps, schema_editor):
    OrderItem = apps.get_model("orders", "OrderItem")
    alias = schema_editor.connection.alias
    for item in OrderItem.objects.using(alias).all().iterator():
        item.total_price = item.unit_price * item.quantity
        item.save(using=alias, update_fields=("total_price",))


class Migration(migrations.Migration):
    dependencies = [("orders", "0007_correct_pos_permissions")]
    operations = [
        migrations.RenameField(model_name="order", old_name="order_code_value", new_name="order_code"),
        migrations.AddField(model_name="orderitem", name="total_price", field=models.DecimalField(decimal_places=0, default=0, max_digits=12, verbose_name="Thành tiền")),
        migrations.AddField(model_name="orderitem", name="updated_at", field=models.DateTimeField(auto_now=True, default=django.utils.timezone.now), preserve_default=False),
        migrations.RunPython(backfill_totals, migrations.RunPython.noop),
    ]
