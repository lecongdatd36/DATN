from decimal import Decimal

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.utils import timezone


def backfill_integrated_data(apps, schema_editor):
    Order = apps.get_model("orders", "Order")
    OrderItem = apps.get_model("orders", "OrderItem")
    Invoice = apps.get_model("orders", "Invoice")
    Payment = apps.get_model("orders", "Payment")
    DiningTable = apps.get_model("seating", "DiningTable")
    Booking = apps.get_model("bookings", "Booking")
    EmployeeProfile = apps.get_model("employees", "EmployeeProfile")
    alias = schema_editor.connection.alias

    employees = dict(EmployeeProfile.objects.using(alias).values_list("user_id", "id"))
    for order in Order.objects.using(alias).select_related("booking").all().iterator():
        booking = order.booking
        items = OrderItem.objects.using(alias).filter(order_id=order.pk).exclude(status="CANCELLED")
        subtotal = sum((item.unit_price * item.quantity for item in items), Decimal("0"))
        order.table_id = booking.table_id if booking else None
        order.customer_id = booking.customer_id if booking else None
        order.employee_id = employees.get(order.created_by_id)
        order.order_code_value = f"DH{order.pk:06d}"
        order.guest_count = booking.party_size if booking else 1
        order.opened_at = booking.seated_at if booking and booking.seated_at else order.created_at
        order.subtotal = subtotal
        order.total_amount = subtotal
        order.status = {"AWAITING_PAYMENT": "PAYMENT_REQUESTED", "PAID": "COMPLETED", "VOID": "CANCELLED"}.get(order.status, order.status)
        if order.status in ("COMPLETED", "CANCELLED"):
            order.closed_at = getattr(booking, "completed_at", None) or order.updated_at
        order.save(using=alias)

    OrderItem.objects.using(alias).filter(status="SENT").update(status="PENDING")
    for invoice in Invoice.objects.using(alias).select_related("order").all().iterator():
        invoice.customer_id = invoice.order.customer_id
        invoice.subtotal = invoice.total
        invoice.total_amount = invoice.total
        invoice.status = {"PENDING": "UNPAID", "VOID": "CANCELLED"}.get(invoice.status, invoice.status)
        invoice.save(using=alias)
    Payment.objects.using(alias).filter(method="TRANSFER").update(method="BANK_TRANSFER")

    DiningTable.objects.using(alias).update(status="AVAILABLE")
    occupied_ids = Booking.objects.using(alias).filter(status="SEATED").values_list("table_id", flat=True)
    DiningTable.objects.using(alias).filter(pk__in=occupied_ids).update(status="OCCUPIED")
    now = timezone.now()
    reserved_ids = Booking.objects.using(alias).filter(status__in=("PENDING", "CONFIRMED"), starts_at__lte=now, ends_at__gt=now).values_list("table_id", flat=True)
    DiningTable.objects.using(alias).filter(pk__in=reserved_ids, status="AVAILABLE").update(status="RESERVED")


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0005_paymentbatch_payment_batch"),
        ("seating", "0003_table_operational_state"),
        ("customers", "0003_membership"),
        ("employees", "0009_rename_manager_position"),
    ]
    operations = [
        migrations.RemoveConstraint(model_name="order", name="order_valid_status"),
        migrations.RemoveConstraint(model_name="orderitem", name="order_item_valid_status"),
        migrations.AlterField(model_name="order", name="booking", field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="order", to="bookings.booking", verbose_name="Lượt khách")),
        migrations.AddField(model_name="order", name="table", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="orders", to="seating.diningtable", verbose_name="Bàn")),
        migrations.AddField(model_name="order", name="customer", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="orders", to="customers.customer", verbose_name="Khách hàng")),
        migrations.AddField(model_name="order", name="employee", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="orders", to="employees.employeeprofile", verbose_name="Nhân viên phục vụ")),
        migrations.AddField(model_name="order", name="order_code_value", field=models.CharField(blank=True, max_length=20, null=True, unique=True, verbose_name="Mã đơn")),
        migrations.AddField(model_name="order", name="guest_count", field=models.PositiveSmallIntegerField(default=1, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(100)], verbose_name="Số khách")),
        migrations.AddField(model_name="order", name="subtotal", field=models.DecimalField(decimal_places=0, default=0, max_digits=14, verbose_name="Tạm tính")),
        migrations.AddField(model_name="order", name="discount_amount", field=models.DecimalField(decimal_places=0, default=0, max_digits=14, verbose_name="Giảm giá")),
        migrations.AddField(model_name="order", name="total_amount", field=models.DecimalField(decimal_places=0, default=0, max_digits=14, verbose_name="Tổng thanh toán")),
        migrations.AddField(model_name="order", name="note", field=models.TextField(blank=True, max_length=1000, verbose_name="Ghi chú")),
        migrations.AddField(model_name="order", name="opened_at", field=models.DateTimeField(blank=True, null=True, verbose_name="Mở lúc")),
        migrations.AddField(model_name="order", name="closed_at", field=models.DateTimeField(blank=True, null=True, verbose_name="Đóng lúc")),
        migrations.AddField(model_name="invoice", name="customer", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="invoices", to="customers.customer")),
        migrations.AddField(model_name="invoice", name="subtotal", field=models.DecimalField(decimal_places=0, default=0, max_digits=12, verbose_name="Tạm tính")),
        migrations.AddField(model_name="invoice", name="discount_percent", field=models.DecimalField(decimal_places=2, default=0, max_digits=5, verbose_name="Phần trăm giảm")),
        migrations.AddField(model_name="invoice", name="discount_amount", field=models.DecimalField(decimal_places=0, default=0, max_digits=12, verbose_name="Tiền giảm")),
        migrations.AddField(model_name="invoice", name="total_amount", field=models.DecimalField(decimal_places=0, default=0, max_digits=12, verbose_name="Cần thanh toán")),
        migrations.CreateModel(
            name="PaymentRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("WAITING", "Đang chờ"), ("PROCESSING", "Đang xử lý"), ("COMPLETED", "Hoàn tất"), ("CANCELLED", "Đã hủy")], db_index=True, default="WAITING", max_length=12)),
                ("requested_at", models.DateTimeField(auto_now_add=True)),
                ("processed_at", models.DateTimeField(blank=True, null=True)),
                ("note", models.TextField(blank=True, max_length=500)),
                ("order", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="payment_requests", to="orders.order")),
                ("requested_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="payment_requests", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-requested_at", "-pk")},
        ),
        migrations.RunPython(backfill_integrated_data, migrations.RunPython.noop),
        migrations.AlterField(model_name="order", name="status", field=models.CharField(choices=[("OPEN", "Đang mở"), ("IN_PROGRESS", "Đang phục vụ"), ("PAYMENT_REQUESTED", "Yêu cầu thanh toán"), ("COMPLETED", "Hoàn tất"), ("CANCELLED", "Đã hủy")], default="OPEN", max_length=20, verbose_name="Trạng thái")),
        migrations.AlterField(model_name="orderitem", name="status", field=models.CharField(choices=[("DRAFT", "Chưa gửi Bếp"), ("PENDING", "Chờ chế biến"), ("COOKING", "Đang làm"), ("READY", "Đã xong"), ("SERVED", "Đã phục vụ"), ("CANCELLED", "Đã hủy")], default="DRAFT", max_length=10, verbose_name="Trạng thái")),
        migrations.AlterField(model_name="invoice", name="status", field=models.CharField(choices=[("UNPAID", "Chưa thanh toán"), ("PAID", "Đã thanh toán"), ("CANCELLED", "Đã hủy")], default="UNPAID", max_length=20, verbose_name="Trạng thái")),
        migrations.AlterField(model_name="payment", name="method", field=models.CharField(choices=[("CASH", "Tiền mặt"), ("CARD", "Thẻ"), ("BANK_TRANSFER", "Chuyển khoản"), ("OTHER", "Khác")], default="CASH", max_length=20, verbose_name="Phương thức")),
        migrations.AddConstraint(model_name="order", constraint=models.CheckConstraint(condition=models.Q(status__in=["OPEN", "IN_PROGRESS", "PAYMENT_REQUESTED", "COMPLETED", "CANCELLED"]), name="order_valid_status")),
        migrations.AddConstraint(model_name="orderitem", constraint=models.CheckConstraint(condition=models.Q(status__in=["DRAFT", "PENDING", "COOKING", "READY", "SERVED", "CANCELLED"]), name="order_item_valid_status")),
        migrations.AddConstraint(model_name="paymentrequest", constraint=models.UniqueConstraint(condition=models.Q(status__in=("WAITING", "PROCESSING")), fields=("order",), name="one_active_payment_request_per_order")),
    ]
