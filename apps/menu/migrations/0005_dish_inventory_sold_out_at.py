from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("menu", "0004_dish_tracks_inventory")]

    operations = [
        migrations.AddField(
            model_name="dish",
            name="inventory_sold_out_at",
            field=models.DateTimeField(blank=True, editable=False, null=True, verbose_name="Tự động hết món do kho lúc"),
        ),
    ]
