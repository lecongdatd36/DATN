from django.db import migrations, models
import django.db.models.deletion
import django.core.validators


class Migration(migrations.Migration):
    dependencies = [("orders", "0010_seed_invoice_view_permission")]

    operations = [
        migrations.AlterField(
            model_name="payment",
            name="method",
            field=models.CharField(
                choices=[
                    ("CASH", "Tiền mặt"),
                    ("CARD", "Thẻ"),
                    ("BANK_TRANSFER", "Chuyển khoản"),
                    ("VNPAY", "VNPAY"),
                    ("OTHER", "Khác"),
                ],
                default="CASH",
                max_length=20,
                verbose_name="Phương thức",
            ),
        ),
        migrations.CreateModel(
            name="OnlinePayment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("txn_ref", models.CharField(max_length=100, unique=True, verbose_name="Mã tham chiếu")),
                ("amount", models.DecimalField(decimal_places=0, max_digits=12, validators=[django.core.validators.MinValueValidator(1)], verbose_name="Số tiền")),
                ("subtotal", models.DecimalField(decimal_places=0, max_digits=12, verbose_name="Tạm tính")),
                ("discount_percent", models.DecimalField(decimal_places=2, default=0, max_digits=5, verbose_name="Phần trăm giảm")),
                ("discount_amount", models.DecimalField(decimal_places=0, default=0, max_digits=12, verbose_name="Tiền giảm")),
                ("status", models.CharField(choices=[("PENDING", "Đang chờ"), ("PAID", "Thành công"), ("FAILED", "Thất bại"), ("CANCELLED", "Đã hủy")], db_index=True, default="PENDING", max_length=12, verbose_name="Trạng thái")),
                ("provider_transaction_no", models.CharField(blank=True, max_length=30, verbose_name="Mã giao dịch VNPAY")),
                ("bank_code", models.CharField(blank=True, max_length=30, verbose_name="Ngân hàng")),
                ("response_code", models.CharField(blank=True, max_length=10, verbose_name="Mã phản hồi")),
                ("raw_response", models.JSONField(blank=True, default=dict, verbose_name="Phản hồi cổng thanh toán")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("paid_at", models.DateTimeField(blank=True, null=True)),
                ("order", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="online_payments", to="orders.order")),
            ],
            options={"verbose_name": "giao dịch trực tuyến", "verbose_name_plural": "giao dịch trực tuyến", "ordering": ("-created_at", "-pk")},
        ),
    ]
