from django.db import migrations


def seed_settings(apps, schema_editor):
    alias = schema_editor.connection.alias
    Settings = apps.get_model("bookings", "BookingSettings")
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")
    Settings.objects.using(alias).get_or_create(pk=1, defaults={"default_duration_minutes": 120})
    content_type, _ = ContentType.objects.using(alias).get_or_create(app_label="bookings", model="bookingsettings")
    permission, _ = Permission.objects.using(alias).get_or_create(
        content_type=content_type, codename="configure_bookings", defaults={"name": "Cấu hình thời lượng đặt bàn"},
    )
    manager, _ = Group.objects.using(alias).get_or_create(name="MANAGER")
    manager.permissions.add(permission)


class Migration(migrations.Migration):
    dependencies = [("bookings", "0004_alter_booking_status_bookingsettings_and_more")]
    operations = [migrations.RunPython(seed_settings, migrations.RunPython.noop)]
