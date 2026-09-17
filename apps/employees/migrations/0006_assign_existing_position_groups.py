from django.db import migrations



def assign_position_groups(apps, schema_editor):
    EmployeeProfile = apps.get_model("employees", "EmployeeProfile")
    User = apps.get_model("accounts", "User")
    for profile in EmployeeProfile.objects.select_related("job_position__group"):
        User.objects.filter(pk=profile.user_id).update(is_staff=profile.job_position.code == "MANAGER")
        profile.user.groups.add(profile.job_position.group)


def remove_position_groups(apps, schema_editor):
    EmployeeProfile = apps.get_model("employees", "EmployeeProfile")
    for profile in EmployeeProfile.objects.select_related("job_position__group"):
        profile.user.groups.remove(profile.job_position.group)


class Migration(migrations.Migration):
    dependencies = [("employees", "0005_remove_employeeprofile_employees_e_job_pos_c9abf4_idx")]
    operations = [migrations.RunPython(assign_position_groups, remove_position_groups)]
