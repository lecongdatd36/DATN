from django.db import migrations


def assign_superuser_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    User = apps.get_model("accounts", "User")
    group = Group.objects.filter(name="MANAGER").first()
    if group:
        for user in User.objects.filter(is_superuser=True):
            user.groups.add(group)


def remove_superuser_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    User = apps.get_model("accounts", "User")
    group = Group.objects.filter(name="MANAGER").first()
    if group:
        for user in User.objects.filter(is_superuser=True):
            user.groups.remove(group)


class Migration(migrations.Migration):
    dependencies = [("employees", "0006_assign_existing_position_groups")]
    operations = [migrations.RunPython(assign_superuser_group, remove_superuser_group)]
