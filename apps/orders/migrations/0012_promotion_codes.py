from django.db import migrations, models
import django.core.validators


def seed_permissions(apps, schema_editor):
    alias = schema_editor.connection.alias
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")
    content_type, _ = ContentType.objects.using(alias).get_or_create(app_label="orders", model="promotioncode")
    permissions = {}
    for action in ("view", "add", "change", "delete"):
        permission, _ = Permission.objects.using(alias).get_or_create(
            content_type=content_type,
            codename=f"{action}_promotioncode",
            defaults={"name": f"Can {action} promotion code"},
        )
        permissions[action] = permission
    manager, _ = Group.objects.using(alias).get_or_create(name="MANAGER")
    manager.permissions.add(*permissions.values())


def seed_tier_view_permissions(apps, schema_editor):
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")
    alias = schema_editor.connection.alias
    permission = Permission.objects.using(alias).filter(
        content_type__app_label="customers", codename="view_membershiptier"
    ).first()
    if permission:
        for code in ("WAITER", "CASHIER"):
            group, _ = Group.objects.using(alias).get_or_create(name=code)
            group.permissions.add(permission)


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0011_online_payment"),
        ("customers", "0004_seed_membership_permissions"),
    ]
    operations = [
        migrations.CreateModel(
            name="PromotionCode",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=30, unique=True, verbose_name="Mã giảm giá")),
                ("name", models.CharField(max_length=150, verbose_name="Tên chương trình")),
                ("discount_type", models.CharField(choices=[("PERCENT", "Phần trăm"), ("FIXED", "Số tiền cố định")], max_length=10, verbose_name="Loại giảm")),
                ("value", models.DecimalField(decimal_places=2, max_digits=12, validators=[django.core.validators.MinValueValidator(0.01)], verbose_name="Giá trị")),
                ("minimum_order", models.DecimalField(decimal_places=0, default=0, max_digits=12, validators=[django.core.validators.MinValueValidator(0)], verbose_name="Đơn tối thiểu")),
                ("maximum_discount", models.DecimalField(blank=True, decimal_places=0, max_digits=12, null=True, validators=[django.core.validators.MinValueValidator(1)], verbose_name="Giảm tối đa")),
                ("starts_at", models.DateTimeField(verbose_name="Bắt đầu")),
                ("ends_at", models.DateTimeField(verbose_name="Kết thúc")),
                ("is_active", models.BooleanField(default=True, verbose_name="Đang áp dụng")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"verbose_name": "mã giảm giá", "verbose_name_plural": "mã giảm giá", "ordering": ("-created_at", "-pk")},
        ),
        migrations.AddConstraint(model_name="promotioncode", constraint=models.CheckConstraint(condition=models.Q(value__gt=0), name="promotion_value_positive")),
        migrations.AddConstraint(model_name="promotioncode", constraint=models.CheckConstraint(condition=models.Q(ends_at__gt=models.F("starts_at")), name="promotion_valid_period")),
        migrations.AddField(model_name="order", name="promotion_code_snapshot", field=models.CharField(blank=True, max_length=30, verbose_name="Mã giảm giá")),
        migrations.AddField(model_name="order", name="promotion_discount_amount", field=models.DecimalField(decimal_places=0, default=0, max_digits=14, verbose_name="Giảm theo mã")),
        migrations.AddField(model_name="invoice", name="membership_discount_amount", field=models.DecimalField(decimal_places=0, default=0, max_digits=12, verbose_name="Ưu đãi hạng")),
        migrations.AddField(model_name="invoice", name="promotion_code", field=models.CharField(blank=True, max_length=30, verbose_name="Mã giảm giá")),
        migrations.AddField(model_name="invoice", name="promotion_discount_amount", field=models.DecimalField(decimal_places=0, default=0, max_digits=12, verbose_name="Giảm theo mã")),
        migrations.AddField(model_name="onlinepayment", name="membership_discount_amount", field=models.DecimalField(decimal_places=0, default=0, max_digits=12, verbose_name="Ưu đãi hạng")),
        migrations.AddField(model_name="onlinepayment", name="promotion_code", field=models.CharField(blank=True, max_length=30, verbose_name="Mã giảm giá")),
        migrations.AddField(model_name="onlinepayment", name="promotion_discount_amount", field=models.DecimalField(decimal_places=0, default=0, max_digits=12, verbose_name="Giảm theo mã")),
        migrations.RunPython(seed_permissions, migrations.RunPython.noop),
        migrations.RunPython(seed_tier_view_permissions, migrations.RunPython.noop),
    ]
