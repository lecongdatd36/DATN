from django.db import migrations, models


def mark_dishes_with_recipes(apps, schema_editor):
    Dish = apps.get_model("menu", "Dish")
    RecipeIngredient = apps.get_model("inventory", "RecipeIngredient")
    alias = schema_editor.connection.alias
    dish_ids = RecipeIngredient.objects.using(alias).values_list("dish_id", flat=True).distinct()
    Dish.objects.using(alias).filter(pk__in=dish_ids).update(tracks_inventory=True)


class Migration(migrations.Migration):
    dependencies = [
        ("menu", "0003_dish_image_dish_thumbnail"),
        ("inventory", "0005_inventorytransaction_source_id_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="dish",
            name="tracks_inventory",
            field=models.BooleanField(
                default=False,
                help_text="Bật để bắt buộc món có ít nhất một nguyên liệu trước khi gửi xuống Bếp.",
                verbose_name="Quản lý tồn kho theo công thức",
            ),
        ),
        migrations.RunPython(mark_dishes_with_recipes, migrations.RunPython.noop),
    ]
