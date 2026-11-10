from decimal import Decimal
from uuid import uuid4
from django.conf import settings
from django.db import models


class ReservationPolicy(models.Model):
    allowed_dishes = models.ManyToManyField("menu.Dish", blank=True, verbose_name="Món cho phép chuẩn bị trước")
    table_deposit = models.PositiveIntegerField("Cọc giữ bàn (đồng)", default=100000)
    ready_percent = models.PositiveSmallIntegerField("Cọc món chuẩn bị trước (%)", default=50)
    hold_minutes = models.PositiveSmallIntegerField("Phút giữ chỗ chờ cọc", default=10)
    offer_minutes = models.PositiveSmallIntegerField("Phút hiệu lực bản chốt", default=30)
    minimum_lead_minutes = models.PositiveSmallIntegerField("Đặt món sẵn trước ít nhất (phút)", default=60)
    free_cancel_hours = models.PositiveSmallIntegerField("Hủy giữ bàn miễn phí trước (giờ)", default=2)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(pk=1), name="reservation_policy_singleton"), models.CheckConstraint(condition=models.Q(ready_percent__gte=1, ready_percent__lte=100, hold_minutes__gte=1, offer_minutes__gte=1, table_deposit__gte=1), name="reservation_policy_ranges")]


class Reservation(models.Model):
    class Mode(models.TextChoices):
        TABLE = "TABLE", "Đến mới chế biến"
        READY = "READY", "Chuẩn bị món theo giờ hẹn"

    class Status(models.TextChoices):
        REVIEW = "REVIEW", "Chờ nhà hàng xem xét"
        OFFER = "OFFER", "Chờ khách đồng ý bản chốt"
        WAITING = "WAITING", "Chờ thanh toán cọc"
        CONFIRMED = "CONFIRMED", "Đã xác nhận"
        SEATED = "SEATED", "Đang phục vụ"
        COMPLETED = "COMPLETED", "Hoàn tất"
        CANCELLED = "CANCELLED", "Đã hủy"
        NO_SHOW = "NO_SHOW", "Không đến"
        EXPIRED = "EXPIRED", "Hết hạn"
        REJECTED = "REJECTED", "Nhà hàng từ chối"

    access_token = models.UUIDField(default=uuid4, unique=True, editable=False)
    request_key = models.UUIDField(default=uuid4, unique=True)
    source_digest = models.CharField(max_length=64)
    booking = models.OneToOneField("bookings.Booking", on_delete=models.PROTECT, null=True, blank=True, related_name="online_reservation")
    mode = models.CharField(max_length=8, choices=Mode.choices)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.REVIEW)
    full_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20)
    party_size = models.PositiveSmallIntegerField()
    starts_at = models.DateTimeField()
    duration_minutes = models.PositiveSmallIntegerField(default=120)
    area = models.ForeignKey("seating.Area", on_delete=models.SET_NULL, null=True, blank=True)
    note = models.TextField(blank=True, max_length=500)
    staff_note = models.TextField(blank=True, max_length=1000)
    requested_snapshot = models.JSONField(default=dict)
    policy_snapshot = models.JSONField(default=dict)
    subtotal = models.DecimalField(max_digits=14, decimal_places=0, default=0)
    deposit_required = models.DecimalField(max_digits=14, decimal_places=0, default=0)
    prep_starts_at = models.DateTimeField(null=True, blank=True)
    ready_by = models.DateTimeField(null=True, blank=True)
    offer_expires_at = models.DateTimeField(null=True, blank=True)
    hold_expires_at = models.DateTimeField(null=True, blank=True)
    free_cancel_until = models.DateTimeField(null=True, blank=True)
    revision = models.PositiveIntegerField(default=1)
    accepted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        constraints = [models.CheckConstraint(condition=models.Q(party_size__gte=1, party_size__lte=100, subtotal__gte=0, deposit_required__gte=0), name="reservation_amount_party_ranges")]

    @property
    def code(self):
        return f"OL{self.pk:06d}"

    @property
    def received(self):
        return sum((p.amount for p in self.deposits.all() if p.status in ("PAID", "REVIEW")), Decimal(0))

    @property
    def refunded(self):
        return sum((r.amount for r in self.refunds.all() if r.status == "COMPLETED"), Decimal(0))

    @property
    def allocated(self):
        return sum((a.amount for a in self.allocations.all()), Decimal(0))

    @property
    def balance(self):
        return max(Decimal(0), self.received - self.refunded - self.allocated)


class CurrentItems(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_active=True)


class PreorderItem(models.Model):
    objects = CurrentItems()
    is_active = models.BooleanField(default=True)
    reservation = models.ForeignKey(Reservation, on_delete=models.PROTECT, related_name="items")
    dish = models.ForeignKey("menu.Dish", on_delete=models.PROTECT)
    dish_name = models.CharField(max_length=150)
    dish_code = models.CharField(max_length=20)
    unit_name = models.CharField(max_length=100)
    quantity = models.PositiveSmallIntegerField()
    unit_price = models.DecimalField(max_digits=9, decimal_places=0)
    note = models.CharField(max_length=500, blank=True)
    status = models.CharField(max_length=10, default="SCHEDULED", choices=(("SCHEDULED", "Đã lên lịch"), ("PENDING", "Chờ chế biến"), ("COOKING", "Đang chế biến"), ("READY", "Sẵn sàng"), ("CANCELLED", "Đã hủy")))
    order_item = models.OneToOneField("orders.OrderItem", on_delete=models.PROTECT, null=True, blank=True, related_name="preorder_source")
    sent_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    ready_at = models.DateTimeField(null=True, blank=True)
    inventory_deducted_at = models.DateTimeField(null=True, blank=True)
    inventory_returned_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    unit_cost = models.DecimalField(max_digits=14, decimal_places=0, default=0)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(quantity__gte=1, quantity__lte=100, unit_price__gte=1), name="preorder_item_valid_values")]

    @property
    def total(self):
        return self.quantity*self.unit_price


class IngredientHold(models.Model):
    item = models.ForeignKey(PreorderItem, on_delete=models.PROTECT, related_name="ingredient_holds")
    ingredient = models.ForeignKey("inventory.Ingredient", on_delete=models.PROTECT, related_name="preorder_holds")
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    state = models.CharField(max_length=10, default="HELD", choices=(("HELD", "Đang giữ"), ("CONSUMED", "Đã xuất"), ("RELEASED", "Đã giải phóng")))

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(quantity__gt=0), name="ingredient_hold_positive")]


class DepositPayment(models.Model):
    reservation = models.ForeignKey(Reservation, on_delete=models.PROTECT, related_name="deposits")
    txn_ref = models.CharField(max_length=100, unique=True)
    amount = models.DecimalField(max_digits=14, decimal_places=0)
    status = models.CharField(max_length=8, default="PENDING", choices=(("PENDING", "Chờ trả"), ("PAID", "Đã nhận"), ("REVIEW", "Đã nhận, cần đối soát"), ("FAILED", "Thất bại")))
    revision = models.PositiveIntegerField()
    provider_ref = models.CharField(max_length=100, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(amount__gt=0), name="deposit_payment_positive")]


class DepositAllocation(models.Model):
    reservation = models.ForeignKey(Reservation, on_delete=models.PROTECT, related_name="allocations")
    invoice = models.OneToOneField("orders.Invoice", on_delete=models.PROTECT, related_name="deposit_allocation")
    amount = models.DecimalField(max_digits=14, decimal_places=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(amount__gt=0),name="deposit_allocation_positive")]


class DepositRefund(models.Model):
    reservation = models.ForeignKey(Reservation, on_delete=models.PROTECT, related_name="refunds")
    amount = models.DecimalField(max_digits=14, decimal_places=0)
    reason = models.CharField(max_length=1000)
    status = models.CharField(max_length=10, default="REQUESTED", choices=(("REQUESTED", "Chờ duyệt"), ("APPROVED", "Đã duyệt, chờ hoàn"), ("COMPLETED", "Đã hoàn"), ("REJECTED", "Từ chối")))
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    bank_reference = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(amount__gt=0), name="deposit_refund_positive")]


class ReservationMessage(models.Model):
    reservation = models.ForeignKey(Reservation, on_delete=models.PROTECT, related_name="messages")
    kind = models.CharField(max_length=12, choices=(("CHANGE", "Yêu cầu thay đổi"), ("CANCEL", "Yêu cầu hủy")))
    text = models.CharField(max_length=1000)
    resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class ReservationLog(models.Model):
    reservation = models.ForeignKey(Reservation, on_delete=models.PROTECT, related_name="logs")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    actor_snapshot = models.CharField(max_length=150)
    action = models.CharField(max_length=50)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-pk")
