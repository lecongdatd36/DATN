from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("bookings", "0007_booking_is_walk_in_alter_booking_customer_and_more")]
    operations = [
        migrations.RemoveConstraint(model_name="booking", name="booking_walk_in_status"),
        migrations.AddConstraint(
            model_name="booking",
            constraint=models.CheckConstraint(
                condition=models.Q(is_walk_in=False) | models.Q(status__in=["SEATED", "COMPLETED", "CANCELLED"]),
                name="booking_walk_in_status",
            ),
        ),
    ]
