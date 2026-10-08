from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("bookings", "0008_allow_cancelled_walk_in")]

    operations = [
        migrations.AddIndex(
            model_name="booking",
            index=models.Index(fields=["status", "ends_at"], name="booking_expiry_idx"),
        ),
    ]
