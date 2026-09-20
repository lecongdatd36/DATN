from django.db import migrations


def seed_permissions(apps, schema_editor):
    alias = schema_editor.connection.alias
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")
    permissions = {}
    for model, names in (("booking", ("view_booking", "manage_booking")), ("bookingactivitylog", ("view_bookingactivitylog",))):
        content_type, _ = ContentType.objects.using(alias).get_or_create(app_label="bookings", model=model)
        for codename in names:
            permissions[codename], _ = Permission.objects.using(alias).get_or_create(content_type=content_type, codename=codename, defaults={"name": codename.replace("_", " ")})
    for role in ("MANAGER", "WAITER", "CASHIER"):
        group, _ = Group.objects.using(alias).get_or_create(name=role)
        names = permissions if role == "MANAGER" else ("view_booking", "manage_booking")
        group.permissions.add(*(permissions[name] for name in names))


class Migration(migrations.Migration):
    dependencies = [("bookings", "0001_initial"), ("seating", "0002_seed_seating_permissions"), ("customers", "0002_seed_customer_permissions")]
    operations = [migrations.RunPython(seed_permissions, migrations.RunPython.noop)]
