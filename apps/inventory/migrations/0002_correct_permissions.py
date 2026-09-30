from django.db import migrations


def correct_permissions(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")
    alias = schema_editor.connection.alias
    permissions = {}
    for model, actions in (("ingredient", ("view", "add", "change", "manage")), ("supplier", ("view",)), ("inventorytransaction", ("view",))):
        content_type, _ = ContentType.objects.using(alias).get_or_create(app_label="inventory", model=model)
        for action in actions:
            codename = "manage_inventory" if action == "manage" else f"{action}_{model}"
            permission, _ = Permission.objects.using(alias).get_or_create(content_type=content_type, codename=codename, defaults={"name": codename.replace("_", " ")})
            permissions[codename] = permission
    manager, _ = Group.objects.using(alias).get_or_create(name="MANAGER")
    inventory, _ = Group.objects.using(alias).get_or_create(name="INVENTORY")
    manager.permissions.add(*permissions.values())
    inventory.permissions.add(*(permission for name, permission in permissions.items() if name in ("view_ingredient", "view_supplier", "view_inventorytransaction", "manage_inventory")))


class Migration(migrations.Migration):
    dependencies = [("inventory", "0001_initial")]
    operations = [migrations.RunPython(correct_permissions, migrations.RunPython.noop)]
