from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("bookings", "0009_booking_expiry_index")]

    operations = [
        migrations.AddField(
            model_name="bookingsettings",
            name="no_show_grace_minutes",
            field=models.PositiveSmallIntegerField(
                default=15,
                validators=[MinValueValidator(0), MaxValueValidator(240)],
                verbose_name="Thời gian chờ khách đến (phút)",
            ),
        ),
        migrations.AddField(
            model_name="bookingsettingslog",
            name="previous_no_show_grace_minutes",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="bookingsettingslog",
            name="new_no_show_grace_minutes",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddConstraint(
            model_name="bookingsettings",
            constraint=models.CheckConstraint(
                condition=models.Q(no_show_grace_minutes__gte=0, no_show_grace_minutes__lte=240),
                name="booking_no_show_grace_range",
            ),
        ),
        migrations.AddIndex(
            model_name="booking",
            index=models.Index(fields=["status", "starts_at"], name="booking_no_show_idx"),
        ),
    ]
