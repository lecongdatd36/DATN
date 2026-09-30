import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0013_backfill_membership_discount"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="split_root",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="split_checks",
                to="orders.order",
                verbose_name="Hóa đơn gốc khi tách",
            ),
        ),
        migrations.AddConstraint(
            model_name="order",
            constraint=models.CheckConstraint(
                condition=models.Q(split_root__isnull=True) | ~models.Q(split_root=models.F("id")),
                name="order_split_root_not_self",
            ),
        ),
    ]
