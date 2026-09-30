from django.db import migrations, models


def backfill_membership_discount(apps, schema_editor):
    Invoice = apps.get_model("orders", "Invoice")
    alias = schema_editor.connection.alias
    Invoice.objects.using(alias).filter(
        membership_discount_amount=0,
        promotion_code="",
        discount_amount__gt=0,
    ).update(membership_discount_amount=models.F("discount_amount"))


class Migration(migrations.Migration):
    dependencies = [("orders", "0012_promotion_codes")]
    operations = [migrations.RunPython(backfill_membership_discount, migrations.RunPython.noop)]
