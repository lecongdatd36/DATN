import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0004_order_paid_and_payment_permission"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="PaymentBatch",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("total", models.DecimalField(decimal_places=0, max_digits=14, validators=[django.core.validators.MinValueValidator(1)], verbose_name="Tổng tiền")),
                ("method", models.CharField(choices=[("CASH", "Tiền mặt"), ("CARD", "Thẻ"), ("TRANSFER", "Chuyển khoản"), ("OTHER", "Khác")], default="CASH", max_length=20, verbose_name="Phương thức")),
                ("reference", models.CharField(blank=True, max_length=100, verbose_name="Ghi chú / mã giao dịch")),
                ("actor_snapshot", models.CharField(blank=True, max_length=150, verbose_name="Người thực hiện")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Thời gian thanh toán")),
                ("performed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "lần thanh toán nhiều bàn",
                "verbose_name_plural": "các lần thanh toán nhiều bàn",
                "ordering": ("-created_at", "-pk"),
            },
        ),
        migrations.AddField(
            model_name="payment",
            name="batch",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="payments", to="orders.paymentbatch"),
        ),
    ]
