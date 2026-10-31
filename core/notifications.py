"""Live counts of outstanding work, restricted to the current user's menu."""

from datetime import timedelta

from django.db.models import F
from django.urls import reverse
from django.utils import timezone

from apps.bookings.models import Booking, BookingSettings
from apps.inventory.models import Ingredient
from apps.orders.models import (
    Order, OrderItem, PaymentRequest, QRCheckInRequest, QROrderRequest, QRServiceRequest,
)
from apps.seating.models import DiningTable


def pending_booking_requests():
    now = timezone.now()
    grace = BookingSettings.objects.values_list("no_show_grace_minutes", flat=True).get(pk=1)
    return Booking.objects.filter(
        is_walk_in=False, status=Booking.Status.PENDING, ends_at__gt=now,
        starts_at__gt=now - timedelta(minutes=grace),
    )


def notification_snapshot(access, *, mobile=False):
    counts = dict.fromkeys(("bookings", "sales", "tasks", "payments", "kitchen", "inventory", "tables"), 0)
    entries = []
    now = timezone.now()
    active = (Order.Status.OPEN, Order.Status.IN_PROGRESS)

    def add(key, group, label, count, url):
        if mobile:
            if key == "bookings" and access.get("can_manage_bookings"):
                url = reverse("sales:mobile") + "?page=tasks&bookings=pending#m-bookings"
            elif key == "tables":
                url = reverse("sales:mobile")
        entries.append({"key": key, "label": label, "count": count, "url": url})
        counts[group] += count

    if access["can_view_bookings"]:
        add("bookings", "bookings", "Đặt bàn chờ xác nhận", pending_booking_requests().count(), reverse("bookings:list") + "?status=PENDING")

    if access["can_view_orders"] and access["can_manage_orders"]:
        tasks_url = reverse("sales:mobile") + "?page=tasks"
        add("checkins", "sales", "Khách chờ nhận bàn QR", QRCheckInRequest.objects.filter(
            status=QRCheckInRequest.Status.WAITING_CONFIRMATION, expires_at__gt=now,
        ).count(), tasks_url + "#m-requests")
        add("qr_orders", "sales", "Gọi món QR chờ duyệt", QROrderRequest.objects.filter(
            status=QROrderRequest.Status.WAITING_CONFIRMATION, order__status__in=active,
        ).count(), tasks_url + "#m-requests")
        add("service", "sales", "Yêu cầu phục vụ", QRServiceRequest.objects.filter(
            status=QRServiceRequest.Status.WAITING, order__status__in=active,
        ).count(), tasks_url + "#m-requests")
        add("ready", "sales", "Món chờ mang ra", OrderItem.objects.filter(
            status=OrderItem.Status.READY, order__status__in=active,
        ).count(), tasks_url + "#m-ready")
    counts["tasks"] = counts["sales"]

    if access["can_view_orders"] and access["can_collect_payments"]:
        add("payments", "payments", "Yêu cầu thanh toán", PaymentRequest.objects.filter(
            status=PaymentRequest.Status.WAITING, order__status=Order.Status.PAYMENT_REQUESTED,
        ).count(), reverse("sales:mobile") + "?page=tasks#m-payments")
        counts["sales"] += counts["payments"]

    if access["can_work_kitchen"]:
        add("kitchen", "kitchen", "Món chờ bếp chế biến", OrderItem.objects.filter(
            status=OrderItem.Status.PENDING, order__status__in=active,
        ).count(), reverse("kitchen:workspace") + "#pending")

    if access["can_view_inventory"]:
        add("inventory", "inventory", "Nguyên liệu sắp hết", Ingredient.objects.filter(
            is_active=True, stock_quantity__lte=F("low_stock_threshold"),
        ).count(), reverse("inventory:workspace") + "?low_stock=on")

    if access["can_view_tables"] and (access["can_manage_orders"] or access["can_manage_seating"]):
        add("tables", "tables", "Bàn cần dọn", DiningTable.objects.filter(
            is_active=True, area__is_active=True, status=DiningTable.Status.CLEANING,
        ).count(), reverse("seating:table_list") + "?status=cleaning")

    counts["total"] = sum(entry["count"] for entry in entries)
    return {"counts": counts, "entries": entries}
