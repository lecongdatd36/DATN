from django.db import migrations


def seed_report_permission(apps, schema_editor):
    alias = schema_editor.connection.alias
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")

    content_type, _ = ContentType.objects.using(alias).get_or_create(app_label="reports", model="report")
    permission, _ = Permission.objects.using(alias).get_or_create(
        content_type=content_type,
        codename="view_report",
        defaults={"name": "Xem báo cáo nhà hàng"},
    )
    manager, _ = Group.objects.using(alias).get_or_create(name="MANAGER")
    manager.permissions.add(permission)


def remove_report_permission(apps, schema_editor):
    alias = schema_editor.connection.alias
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")
    permission = Permission.objects.using(alias).filter(
        content_type__app_label="reports",
        codename="view_report",
    ).first()
    manager = Group.objects.using(alias).filter(name="MANAGER").first()
    if permission and manager:
        manager.permissions.remove(permission)


class Migration(migrations.Migration):
    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("employees", "0009_rename_manager_position"),
        ("orders", "0004_order_paid_and_payment_permission"),
    ]
    operations = [migrations.RunPython(seed_report_permission, remove_report_permission)]
