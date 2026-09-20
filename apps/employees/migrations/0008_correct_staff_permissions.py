"""Cấp quyền tường minh, hoạt động cả khi migrate database mới hoàn toàn."""
import apps.employees.validators
from django.db import migrations, models


def correct_permissions(apps, schema_editor):
    alias = schema_editor.connection.alias
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")
    User = apps.get_model("accounts", "User")
    manager_permissions = []
    for app_label, model in (
        ("accounts", "user"), ("employees", "employeeprofile"),
        ("employees", "employeeactivitylog"), ("employees", "jobposition"),
    ):
        content_type, _ = ContentType.objects.using(alias).get_or_create(app_label=app_label, model=model)
        permission, _ = Permission.objects.using(alias).get_or_create(
            content_type=content_type, codename=f"view_{model}",
            defaults={"name": f"Can view {model}"},
        )
        manager_permissions.append(permission)
        if model == "employeeprofile":
            permission, _ = Permission.objects.using(alias).get_or_create(
                content_type=content_type, codename="manage_staff",
                defaults={"name": "Quản lý tài khoản và nhân viên"},
            )
            manager_permissions.append(permission)
    old_permissions = list(Permission.objects.using(alias).filter(
        content_type__app_label__in=("accounts", "employees"),
    ))
    for code in ("MANAGER", "WAITER", "CASHIER", "KITCHEN", "INVENTORY"):
        group, _ = Group.objects.using(alias).get_or_create(name=code)
        group.permissions.remove(*old_permissions)
        if code == "MANAGER":
            group.permissions.add(*manager_permissions)
    # Phiên đã được mở với quyền cũ phải đăng nhập lại sau bản sửa phân quyền.
    User.objects.using(alias).all().update(session_version=models.F("session_version") + 1)


class Migration(migrations.Migration):
    dependencies = [("employees", "0007_assign_superuser_manager_group")]
    operations = [
        migrations.AlterModelOptions(
            name="employeeprofile",
            options={"ordering": ("employee_code", "pk"), "permissions": [("manage_staff", "Quản lý tài khoản và nhân viên")]},
        ),
        migrations.AlterField(
            model_name="employeeprofile", name="avatar",
            field=models.ImageField(blank=True, upload_to="employees/", validators=[apps.employees.validators.validate_avatar], verbose_name="ảnh đại diện"),
        ),
        migrations.RunPython(correct_permissions, migrations.RunPython.noop),
    ]
