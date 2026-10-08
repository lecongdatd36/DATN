import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def populate_client_request_ids(apps, schema_editor):
    QROrderRequest = apps.get_model("orders", "QROrderRequest")
    for request in QROrderRequest.objects.filter(client_request_id__isnull=True).iterator():
        request.client_request_id = uuid.uuid4()
        request.save(update_fields=("client_request_id",))


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("orders", "0019_qrcheckinrequest"),
    ]

    operations = [
        migrations.AddField(
            model_name="qrorderrequest",
            name="client_request_id",
            field=models.UUIDField(editable=False, null=True),
        ),
        migrations.RunPython(populate_client_request_ids, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="qrorderrequest",
            name="client_request_id",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.CreateModel(
            name="QRServiceRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("request_type", models.CharField(choices=[("STAFF", "Gọi nhân viên"), ("WATER", "Xin thêm nước"), ("ICE", "Xin thêm đá"), ("BOWLS", "Xin thêm chén"), ("OTHER", "Yêu cầu khác")], max_length=12)),
                ("note", models.CharField(blank=True, max_length=300)),
                ("status", models.CharField(choices=[("WAITING", "Đang chờ nhân viên"), ("COMPLETED", "Đã xử lý"), ("CANCELLED", "Đã hủy")], db_index=True, default="WAITING", max_length=12)),
                ("client_request_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("completed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="completed_qr_service_requests", to=settings.AUTH_USER_MODEL)),
                ("order", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="qr_service_requests", to="orders.order")),
                ("table", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="qr_service_requests", to="seating.diningtable")),
            ],
            options={
                "verbose_name": "yêu cầu phục vụ QR",
                "verbose_name_plural": "yêu cầu phục vụ QR",
                "ordering": ("created_at", "pk"),
            },
        ),
        migrations.AddConstraint(
            model_name="qrservicerequest",
            constraint=models.CheckConstraint(condition=models.Q(("request_type__in", ("STAFF", "WATER", "ICE", "BOWLS", "OTHER"))), name="qr_service_request_valid_type"),
        ),
        migrations.AddConstraint(
            model_name="qrservicerequest",
            constraint=models.CheckConstraint(condition=models.Q(("status__in", ("WAITING", "COMPLETED", "CANCELLED"))), name="qr_service_request_valid_status"),
        ),
        migrations.AddConstraint(
            model_name="qrservicerequest",
            constraint=models.UniqueConstraint(condition=models.Q(("status", "WAITING")), fields=("table", "request_type"), name="one_waiting_qr_service_per_table_type"),
        ),
    ]
