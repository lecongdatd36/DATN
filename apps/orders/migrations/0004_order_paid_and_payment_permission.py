from django.db import migrations, models


def seed_payment_permission(apps, schema_editor):
    alias = schema_editor.connection.alias
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")
    content_type, _ = ContentType.objects.using(alias).get_or_create(app_label="orders", model="order")
    permission, _ = Permission.objects.using(alias).get_or_create(
        content_type=content_type,
        codename="collect_payment",
        defaults={"name": "Thu tiền đơn hàng"},
    )
    for code in ("MANAGER", "CASHIER"):
        group, _ = Group.objects.using(alias).get_or_create(name=code)
        group.permissions.add(permission)


class Migration(migrations.Migration):
    dependencies = [("orders", "0003_invoice_payment")]

    operations = [
        migrations.AlterModelOptions(
            name="order",
            options={
                "ordering": ("-created_at", "-pk"),
                "permissions": [
                    ("manage_order", "Mở đơn và gọi món"),
                    ("collect_payment", "Thu tiền đơn hàng"),
                    ("work_kitchen", "Xử lý món tại Bếp"),
                    ("cancel_prepared_item", "Hủy món đã bắt đầu làm"),
                ],
                "verbose_name": "đơn hàng",
                "verbose_name_plural": "đơn hàng",
            },
        ),
        migrations.RemoveConstraint(model_name="order", name="order_valid_status"),
        migrations.AlterField(
            model_name="order",
            name="status",
            field=models.CharField(
                choices=[
                    ("OPEN", "Đang phục vụ"),
                    ("AWAITING_PAYMENT", "Chờ thanh toán"),
                    ("PAID", "Đã thanh toán"),
                    ("VOID", "Đã hủy"),
                ],
                default="OPEN",
                max_length=20,
                verbose_name="Trạng thái",
            ),
        ),
        migrations.AddConstraint(
            model_name="order",
            constraint=models.CheckConstraint(
                condition=models.Q(status__in=["OPEN", "AWAITING_PAYMENT", "PAID", "VOID"]),
                name="order_valid_status",
            ),
        ),
        migrations.RunPython(seed_payment_permission, migrations.RunPython.noop),
    ]
