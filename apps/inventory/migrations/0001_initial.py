import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def seed_inventory_permissions(apps, schema_editor):
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")
    alias = schema_editor.connection.alias
    permissions = Permission.objects.using(alias).filter(content_type__app_label="inventory")
    manager, _ = Group.objects.using(alias).get_or_create(name="MANAGER")
    inventory, _ = Group.objects.using(alias).get_or_create(name="INVENTORY")
    manager.permissions.add(*permissions)
    inventory.permissions.add(*permissions.filter(codename__in=("view_ingredient", "view_supplier", "view_inventorytransaction", "manage_inventory")))


class Migration(migrations.Migration):
    initial = True
    dependencies = [("employees", "0009_rename_manager_position"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(name="Supplier", fields=[("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("name", models.CharField(max_length=150, verbose_name="Tên nhà cung cấp")), ("phone", models.CharField(blank=True, max_length=20, verbose_name="Số điện thoại")), ("address", models.CharField(blank=True, max_length=255, verbose_name="Địa chỉ")), ("is_active", models.BooleanField(default=True, verbose_name="Đang hợp tác")), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True))], options={"verbose_name": "nhà cung cấp", "verbose_name_plural": "nhà cung cấp", "ordering": ("name", "pk")}),
        migrations.CreateModel(name="Ingredient", fields=[("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("code", models.CharField(max_length=20, unique=True, verbose_name="Mã nguyên liệu")), ("name", models.CharField(max_length=150, verbose_name="Tên nguyên liệu")), ("unit", models.CharField(max_length=30, verbose_name="Đơn vị tính")), ("stock_quantity", models.DecimalField(decimal_places=3, default=0, max_digits=14, verbose_name="Tồn kho")), ("low_stock_threshold", models.DecimalField(decimal_places=3, default=0, max_digits=14, verbose_name="Ngưỡng sắp hết")), ("is_active", models.BooleanField(default=True, verbose_name="Đang sử dụng")), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True))], options={"verbose_name": "nguyên liệu", "verbose_name_plural": "nguyên liệu", "ordering": ("name", "pk"), "permissions": [("manage_inventory", "Nhập, xuất và điều chỉnh kho")]}),
        migrations.CreateModel(name="InventoryTransaction", fields=[("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("transaction_type", models.CharField(choices=[("IMPORT", "Nhập kho"), ("EXPORT", "Xuất kho"), ("ADJUSTMENT", "Điều chỉnh")], max_length=12, verbose_name="Loại giao dịch")), ("quantity", models.DecimalField(decimal_places=3, max_digits=14, verbose_name="Số lượng")), ("stock_before", models.DecimalField(decimal_places=3, max_digits=14, verbose_name="Tồn trước")), ("stock_after", models.DecimalField(decimal_places=3, max_digits=14, verbose_name="Tồn sau")), ("unit_cost", models.DecimalField(decimal_places=0, default=0, max_digits=14, validators=[django.core.validators.MinValueValidator(0)], verbose_name="Đơn giá")), ("note", models.TextField(blank=True, max_length=500, verbose_name="Ghi chú")), ("created_at", models.DateTimeField(auto_now_add=True)), ("ingredient", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="transactions", to="inventory.ingredient")), ("performed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)), ("supplier", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="transactions", to="inventory.supplier"))], options={"verbose_name": "giao dịch kho", "verbose_name_plural": "giao dịch kho", "ordering": ("-created_at", "-pk")}),
        migrations.AddConstraint(model_name="ingredient", constraint=models.CheckConstraint(condition=models.Q(stock_quantity__gte=0), name="inventory_stock_nonnegative")),
        migrations.AddConstraint(model_name="ingredient", constraint=models.CheckConstraint(condition=models.Q(low_stock_threshold__gte=0), name="inventory_threshold_nonnegative")),
        migrations.RunPython(seed_inventory_permissions, migrations.RunPython.noop),
    ]
