import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("customers", "0002_seed_customer_permissions")]
    operations = [
        migrations.CreateModel(
            name="MembershipTier",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100, unique=True, verbose_name="Tên hạng")),
                ("minimum_spending", models.DecimalField(decimal_places=0, default=0, max_digits=14, verbose_name="Mức chi tiêu tối thiểu")),
                ("discount_percent", models.DecimalField(decimal_places=2, default=0, max_digits=5, verbose_name="Phần trăm giảm")),
                ("is_active", models.BooleanField(default=True, verbose_name="Đang áp dụng")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"verbose_name": "hạng thành viên", "verbose_name_plural": "hạng thành viên", "ordering": ("minimum_spending", "pk")},
        ),
        migrations.AddConstraint(model_name="membershiptier", constraint=models.CheckConstraint(condition=models.Q(minimum_spending__gte=0), name="membership_minimum_nonnegative")),
        migrations.AddConstraint(model_name="membershiptier", constraint=models.CheckConstraint(condition=models.Q(discount_percent__gte=0, discount_percent__lte=100), name="membership_discount_range")),
        migrations.AddField(model_name="customer", name="membership_tier", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="customers", to="customers.membershiptier", verbose_name="Hạng thành viên")),
        migrations.AddField(model_name="customer", name="total_spending", field=models.DecimalField(decimal_places=0, default=0, max_digits=14, verbose_name="Tổng chi tiêu")),
    ]
