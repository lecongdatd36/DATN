from django.db import migrations


def rename_manager(apps, schema_editor):
    JobPosition = apps.get_model("employees", "JobPosition")
    JobPosition.objects.using(schema_editor.connection.alias).filter(code="MANAGER").update(name="Quản lí")


def restore_manager_name(apps, schema_editor):
    JobPosition = apps.get_model("employees", "JobPosition")
    JobPosition.objects.using(schema_editor.connection.alias).filter(code="MANAGER", name="Quản lí").update(name="Quản trị viên / Quản lý")


class Migration(migrations.Migration):
    dependencies = [("employees", "0008_correct_staff_permissions")]
    operations = [migrations.RunPython(rename_manager, restore_manager_name)]
