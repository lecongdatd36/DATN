from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("seating", "0002_seed_seating_permissions")]
    operations = [
        migrations.AddField(model_name="diningtable", name="name", field=models.CharField(blank=True, max_length=100, verbose_name="Tên bàn")),
        migrations.AddField(model_name="diningtable", name="status", field=models.CharField(choices=[("AVAILABLE", "Trống"), ("RESERVED", "Đã đặt"), ("OCCUPIED", "Đang phục vụ"), ("CLEANING", "Cần dọn")], db_index=True, default="AVAILABLE", max_length=12, verbose_name="Trạng thái")),
        migrations.AddConstraint(model_name="diningtable", constraint=models.CheckConstraint(condition=models.Q(status__in=["AVAILABLE", "RESERVED", "OCCUPIED", "CLEANING"]), name="seating_table_valid_status")),
    ]
