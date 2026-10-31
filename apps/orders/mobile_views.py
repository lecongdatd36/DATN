"""Mobile staff screens. All mutations reuse the restaurant's existing services."""
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.http import JsonResponse
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.decorators.cache import never_cache
from django.utils.decorators import method_decorator

from apps.bookings.models import Booking
from apps.bookings.permissions import has_booking_permission
from apps.bookings.services import transition_booking
from apps.customers.models import Customer
from apps.customers.services import create_customer
from apps.customers.validators import normalize_phone
from apps.seating.models import Area, DiningTable
from core.menu_lock import lock_menu
from core.seating_lock import lock_seating_schedule
from . import services
from .models import Invoice, OnlinePayment, Order, OrderActivityLog, OrderItem, QRCheckInRequest
from .permissions import has_order_permission
from .sales_views import SalesAccessMixin, SalesWorkspaceView, _error_text


def mobile_url(page="tables", **params):
    return reverse("sales:mobile") + "?" + urlencode({"page": page, **{key: value for key, value in params.items() if value is not None}})


def payment_quote(order, promotion=None):
    invoice = getattr(order, "invoice", None)
    if invoice and invoice.paid_amount > 0:
        if promotion is not None and promotion != invoice.promotion_code:
            raise ValidationError("Hóa đơn đã thu một phần nên không thể đổi ưu đãi.")
        return {"subtotal": invoice.subtotal, "discount": invoice.discount_amount,
                "due": invoice.remaining, "promotion_code": invoice.promotion_code,
                "paid": invoice.paid_amount, "locked": True}
    preview = services.payment_preview(order, promotion_code=promotion)
    return {**preview, "paid": Decimal("0"), "locked": False}


@method_decorator(never_cache, name="dispatch")
class MobileWorkspaceView(SalesWorkspaceView):
    template_name = "staff/mobile/workspace.html"

    def dispatch(self, request, *args, **kwargs):
        for key in ("order", "table", "checkin", "invoice"):
            value = request.GET.get(key)
            if value and (not value.isdecimal() or len(value) > 19 or not 0 < int(value) < 2**63):
                raise Http404("Thông tin bàn hoặc order không hợp lệ.")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        requested_page = self.request.GET.get("page", "order" if self.request.GET.get("order") or self.request.GET.get("table") else "tables")
        self.compact_workspace = requested_page in {"open", "menu", "order", "checkout", "split", "invoices", "receipt", "personal"}
        context = super().get_context_data(**kwargs)
        order = context["selected_order"]
        page = self.request.GET.get("page", "order" if order else "tables")
        if page not in {"tables", "open", "menu", "order", "checkout", "split", "tasks", "payments", "invoices", "receipt", "personal"}:
            page = "tables"
        if page in {"checkout", "split", "payments", "invoices", "receipt"} and not context["can_collect_payment"]:
            raise PermissionDenied("Chức năng này cần quyền thu tiền.")
        if page in {"menu", "order", "checkout", "split"} and order is None:
            page = "tables"
        if page == "tables" and self.compact_workspace:
            self.compact_workspace = False
            context = super().get_context_data(**kwargs)
            order = context["selected_order"]
        if page == "open":
            if not context["can_manage_order"]:
                raise PermissionDenied("Bạn chưa có quyền nhận bàn.")
            context["opening_table"] = get_object_or_404(DiningTable.objects.select_related("area"), pk=self.request.GET.get("table"), is_active=True, area__is_active=True)
            context["checkin_id"] = self.request.GET.get("checkin", "")
            context["opening_guests"] = 1
            if context["checkin_id"]:
                checkin = get_object_or_404(QRCheckInRequest, pk=context["checkin_id"], table=context["opening_table"],
                                           status=QRCheckInRequest.Status.WAITING_CONFIRMATION, expires_at__gt=timezone.now())
                context["opening_guests"] = checkin.guest_count
        context.update(mobile_page=page, mobile_areas=Area.objects.filter(is_active=True),
                       mobile_tables=list(context.get("tables", [])) if page == "tables" else [],
                       mobile_can_book=has_booking_permission(self.request.user, "manage_booking"),
                       mobile_template=f"staff/mobile/{page}.html", mobile_in_order=page in {"menu", "order", "checkout", "split"})
        if page == "tables" and "active_orders" in context:
            context["mobile_table_stats"] = {
                status: sum(table.status == status for table in context["mobile_tables"])
                for status in ("AVAILABLE", "OCCUPIED", "RESERVED")
            }
            by_table = {}
            for active in context["active_orders"]:
                by_table.setdefault(active.table_id, []).append(active)
            for table in context["mobile_tables"]:
                checks = by_table.get(table.pk, [])
                table.mobile_subtotal = sum((check.total for check in checks), Decimal("0"))
                table.mobile_guests = max((check.guest_count for check in checks), default=0)
        if order:
            context["mobile_quote"] = payment_quote(order)
            context["mobile_payment_pending"] = order.online_payments.filter(status=OnlinePayment.Status.PENDING).exists()
            context["mobile_can_pay"] = context["selected_can_request_payment"] and not context["mobile_payment_pending"]
            group = context["selected_split_group"]
            for check in group:
                check.mobile_due = payment_quote(check)["due"]
            context["mobile_group"] = group
            if page == "menu":
                from apps.menu.models import Category, Dish
                context["categories"] = Category.objects.filter(is_active=True)
                context["dishes"] = Dish.objects.filter(status=Dish.Status.AVAILABLE, category__is_active=True, unit__is_active=True).select_related("category", "unit")
                quantities = {}
                for item in order.items.all():
                    if item.status == OrderItem.Status.DRAFT:
                        quantities[item.dish_id] = quantities.get(item.dish_id, 0) + item.quantity
                dishes = list(context["dishes"])
                for dish in dishes:
                    dish.mobile_quantity = quantities.get(dish.pk, 0)
                context["dishes"] = dishes
        if page == "payments":
            checks = list(context["active_orders"])
            pending_ids = set(OnlinePayment.objects.filter(
                order_id__in=[check.pk for check in checks], status=OnlinePayment.Status.PENDING
            ).values_list("order_id", flat=True))
            for check in checks:
                live = [item for item in check.items.all() if item.status != OrderItem.Status.CANCELLED]
                check.mobile_unserved = [item for item in live if item.status != OrderItem.Status.SERVED]
                check.mobile_quantity = sum(item.quantity for item in live)
                check.mobile_pending = check.pk in pending_ids
                check.mobile_can_pay = bool(live) and not check.mobile_unserved and not check.mobile_pending
                check.mobile_due = payment_quote(check)["due"]
            context["mobile_checks"] = sorted(checks, key=lambda check: not check.mobile_can_pay)
        if page == "tasks":
            context["ready_items"] = OrderItem.objects.filter(status=OrderItem.Status.READY, order__status__in=(Order.Status.OPEN, Order.Status.IN_PROGRESS)).select_related("order__table__area", "dish").order_by("ready_at", "pk")
            context["mobile_bookings"] = Booking.objects.filter(is_walk_in=False, starts_at__date=timezone.localdate(), status__in=(Booking.Status.PENDING, Booking.Status.CONFIRMED)).select_related("table__area", "customer") if context["mobile_can_book"] else []
            if context["mobile_can_book"] and self.request.GET.get("bookings") == "pending":
                from core.notifications import pending_booking_requests
                context["mobile_bookings"] = pending_booking_requests().select_related("table__area", "customer").order_by("starts_at", "pk")
                context["mobile_pending_bookings"] = True
        if page == "invoices":
            invoices = Invoice.objects.filter(status=Invoice.Status.PAID).select_related("order__table", "customer").order_by("-closed_at", "-pk")
            query = self.request.GET.get("q", "").strip()
            if query:
                from django.db.models import Q
                invoices = invoices.filter(Q(invoice_code__icontains=query) | Q(order__table__code__icontains=query) | Q(customer__phone__icontains=query))
            context["invoice_page"] = Paginator(invoices, 20).get_page(self.request.GET.get("p"))
        if page == "receipt":
            context["mobile_invoice"] = get_object_or_404(Invoice.objects.select_related("order__table", "customer"), pk=self.request.GET.get("invoice"), status=Invoice.Status.PAID)
            tender = self.request.session.get("mobile_tender", {})
            if tender.get("invoice") == context["mobile_invoice"].pk:
                context["mobile_tender"] = {**tender, "cash": Decimal(tender["cash"]), "change": Decimal(tender["change"])}
        return context


class MobileQuoteView(SalesAccessMixin, View):
    permission = "collect_payment"

    def get(self, request):
        value = request.GET.get("order", "")
        if not value.isdecimal() or len(value) > 19 or not 0 < int(value) < 2**63:
            raise Http404("Order không hợp lệ.")
        order = get_object_or_404(Order.objects.select_related("customer", "invoice"), pk=request.GET.get("order"))
        try:
            if order.status not in (Order.Status.OPEN, Order.Status.IN_PROGRESS, Order.Status.PAYMENT_REQUESTED):
                raise ValidationError("Order đã kết thúc. Hãy kiểm tra lại hóa đơn.")
            quote = payment_quote(order, request.GET.get("promotion", "").strip().upper())
        except ValidationError as error:
            return JsonResponse({"ok": False, "error": _error_text(error)}, status=400)
        return JsonResponse({"ok": True, "revision": order.revision, "subtotal": str(quote["subtotal"]),
                             "discount": str(quote["discount"]), "due": str(quote["due"]),
                             "promotion": quote["promotion_code"]})


class MobileActionView(SalesAccessMixin, View):
    """PRG without JS; JSON navigation and inline menu updates with JS."""
    collection_actions = {"pay", "split", "merge", "prepare-split"}

    def post(self, request, action):
        permission = "collect_payment" if action in self.collection_actions else "manage_order"
        if not has_order_permission(request.user, permission):
            raise PermissionDenied("Bạn chưa có quyền thực hiện thao tác này.")
        try:
            with transaction.atomic():
                # Match services' seating -> menu -> actor -> order lock order.
                lock_seating_schedule()
                lock_menu()
                get_user_model().objects.select_for_update().get(pk=request.user.pk)
                payload = self.perform(request, action)
        except PermissionDenied as error:
            return self.failure(request, str(error), 403)
        except (ValidationError, ObjectDoesNotExist, TypeError, ValueError, InvalidOperation, KeyError) as error:
            message = _error_text(error) if isinstance(error, ValidationError) else "Dữ liệu không còn hợp lệ. Hãy cập nhật để kiểm tra lại."
            return self.failure(request, message, 409)
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"ok": True, **payload})
        messages.success(request, payload.get("message", "Đã cập nhật."))
        return redirect(payload["url"])

    def failure(self, request, message, status):
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"ok": False, "error": message}, status=status)
        messages.error(request, message)
        return redirect(mobile_url())

    def locked_order(self, request):
        order = Order.objects.select_for_update(of=("self",)).select_related("customer", "invoice").get(pk=int(request.POST["order_id"]))
        if order.revision != int(request.POST["expected_revision"]):
            raise ValidationError("Order vừa được cập nhật từ thiết bị khác. Hãy cập nhật và kiểm tra lại trước khi xác nhận.")
        return order

    def open_table(self, request, table_id=None):
        customer = None
        raw_phone = request.POST.get("customer_phone", "").strip()
        if raw_phone:
            phone = normalize_phone(raw_phone)
            customer = Customer.objects.filter(phone=phone).first()
            if customer is None:
                customer = create_customer(actor=request.user, full_name=request.POST.get("customer_name", ""), phone=phone)
        note = request.POST.get("note", "").strip()
        if len(note) > 1000:
            raise ValidationError("Ghi chú bàn không được vượt quá 1000 ký tự.")
        return services.open_table(actor=request.user, table_id=table_id or int(request.POST["table_id"]),
                                   guest_count=int(request.POST["guest_count"]), customer_id=customer.pk if customer else None, note=note)

    def perform(self, request, action):
        data, actor = request.POST, request.user
        if action == "open":
            checkin = None
            if data.get("checkin_id"):
                checkin = QRCheckInRequest.objects.select_for_update().get(pk=int(data["checkin_id"]))
                if checkin.table_id != int(data["table_id"]) or checkin.status != QRCheckInRequest.Status.WAITING_CONFIRMATION:
                    raise ValidationError("Yêu cầu QR không còn hợp lệ.")
            order = self.open_table(request)
            if checkin:
                services.confirm_qr_check_in_request(actor=actor, request_id=checkin.pk)
            return {"url": mobile_url("menu", order=order.pk)}
        if action in {"booking-seat", "booking-confirm"}:
            if not has_booking_permission(actor, "manage_booking"):
                raise PermissionDenied("Bạn chưa có quyền nhận khách đặt trước.")
            if action == "booking-confirm":
                transition_booking(actor=actor, booking_id=int(data["booking_id"]), target=Booking.Status.CONFIRMED,
                                   expected_status=data["expected_status"], expected_revision=int(data["expected_revision"]))
                return {"url": mobile_url("tasks")}
            note = data.get("note", "").strip()
            if len(note) > 1000:
                raise ValidationError("Ghi chú bàn không được vượt quá 1000 ký tự.")
            if data.get("verified") != "yes":
                raise ValidationError("Đối chiếu thông tin khách và mã đặt trước khi nhận bàn.")
            booking = transition_booking(actor=actor, booking_id=int(data["booking_id"]), target=Booking.Status.SEATED,
                                         expected_status=data["expected_status"], expected_revision=int(data["expected_revision"]))
            order = services.open_order(actor=actor, booking_id=booking.pk)
            if note:
                order.note = note
                order.full_clean()
                order.save(update_fields=("note", "updated_at"))
                OrderActivityLog.objects.create(order=order, action="Ghi chú nhận khách", description=note, performed_by=actor, actor_snapshot=actor.username)
            return {"url": mobile_url("menu", order=order.pk)}
        if action in {"qr-confirm", "qr-reject", "qr-checkin", "qr-checkin-reject", "service-complete"}:
            request_id = int(data["request_id"])
            if action == "qr-confirm":
                result = services.confirm_qr_order_request(actor=actor, request_id=request_id)
                return {"url": mobile_url("order", order=result.order_id)}
            if action == "qr-checkin":
                result = services.confirm_qr_check_in_request(actor=actor, request_id=request_id)
                return {"url": mobile_url("menu", order=result.order_id)}
            if action == "qr-reject":
                services.reject_qr_order_request(actor=actor, request_id=request_id, reason=data.get("reason", ""))
            elif action == "qr-checkin-reject":
                services.reject_qr_check_in_request(actor=actor, request_id=request_id, reason=data.get("reason", ""))
            else:
                services.complete_qr_service_request(actor=actor, request_id=request_id)
            return {"url": mobile_url("tasks")}
        if action == "clean":
            services.finish_cleaning(actor=actor, table_id=int(data["table_id"]))
            return {"url": mobile_url()}
        order = self.locked_order(request)
        common = {"actor": actor, "order_id": order.pk, "expected_revision": order.revision}
        if action == "pay":
            return self.collect(request, order)
        if action == "prepare-split":
            services.prepare_quick_payment(actor=actor, order_id=order.pk)
            return {"url": mobile_url("split", order=order.pk)}
        if action == "split":
            quantities = {int(key.removeprefix("quantity_")): int(value) for key, value in data.items() if key.startswith("quantity_")}
            child = services.split_order(**common, quantities=quantities)
            return {"url": mobile_url("checkout", order=child.pk)}
        if action == "merge":
            root = services.merge_split_order(**common)
            return {"url": mobile_url("order", order=root.pk)}
        if action == "add":
            services.add_item(**common, dish_id=int(data["dish_id"]), quantity=int(data.get("quantity", 1)), note=data.get("note", ""))
        elif action == "edit":
            services.edit_item(**common, item_id=int(data["item_id"]), quantity=int(data["quantity"]), note=data.get("note", ""))
        elif action == "remove":
            services.remove_draft_item(**common, item_id=int(data["item_id"]))
        elif action == "send":
            services.send_to_kitchen(**common)
        elif action in {"served", "cancel-item"}:
            services.transition_item(**common, item_id=int(data["item_id"]), target=OrderItem.Status.SERVED if action == "served" else OrderItem.Status.CANCELLED, reason=data.get("reason", ""))
            if action == "served" and data.get("return_page") == "tasks":
                return {"url": mobile_url("tasks")}
        elif action == "request-payment":
            services.request_payment(**common)
        elif action == "move":
            services.move_table(actor=actor, order_id=order.pk, target_table_id=int(data["target_table_id"]))
        elif action == "cancel":
            services.cancel_table_order(**common, reason=data.get("reason", ""))
            return {"url": mobile_url()}
        else:
            raise ValidationError("Thao tác mobile không hợp lệ.")
        order.refresh_from_db()
        items = list(order.items.all())
        return {"url": mobile_url("order", order=order.pk), "revision": order.revision,
                "due": str(payment_quote(order)["due"]),
                "draft_count": sum(item.quantity for item in items if item.status == OrderItem.Status.DRAFT)}

    def collect(self, request, order):
        data = request.POST
        method = data.get("payment_method")
        if method not in ("CASH", "BANK_TRANSFER"):
            raise ValidationError("Mobile chỉ hỗ trợ tiền mặt hoặc chuyển khoản.")
        if order.online_payments.filter(status=OnlinePayment.Status.PENDING).exists():
            raise ValidationError("Hóa đơn đang có giao dịch trực tuyến chờ kết quả. Không thu thêm tiền cho đến khi xử lý xong.")
        live_items = order.items.exclude(status=OrderItem.Status.CANCELLED)
        if not live_items.exists() or live_items.exclude(status=OrderItem.Status.SERVED).exists():
            raise ValidationError("Cần phục vụ xong tất cả món trước khi thu tiền.")
        if order.customer_id:
            Customer.objects.select_for_update().get(pk=order.customer_id)
        promotion = data.get("promotion_code", "").strip().upper()
        quote = payment_quote(order, promotion)
        reviewed = Decimal(data["reviewed_total"])
        if not reviewed.is_finite() or reviewed != quote["due"]:
            raise ValidationError("Số tiền đã thay đổi. Hãy cập nhật tạm tính và xác nhận lại.")
        cash = Decimal("0")
        if method == "CASH":
            cash = Decimal(data.get("cash_received", ""))
            if not cash.is_finite() or cash != cash.to_integral_value() or cash < reviewed:
                raise ValidationError("Tiền khách đưa phải là số nguyên đồng và đủ số cần thu.")
        elif data.get("received_transfer") != "yes":
            raise ValidationError("Cần xác nhận đã nhận đủ tiền vào tài khoản nhà hàng.")
        before_paid = getattr(order, "invoice", None)
        before_paid = before_paid.paid_amount if before_paid else Decimal("0")
        services.prepare_quick_payment(actor=request.user, order_id=order.pk)
        invoice = services.process_payment(actor=request.user, order_id=order.pk, payment_method=method,
                                           transaction_code=data.get("transaction_code", ""), promotion_code=promotion)
        invoice.refresh_from_db()
        if invoice.paid_amount - before_paid != reviewed:
            raise ValidationError("Ưu đãi hoặc số tiền vừa thay đổi. Giao dịch chưa được ghi nhận; hãy kiểm tra lại.")
        request.session["mobile_tender"] = {"invoice": invoice.pk, "cash": str(cash), "change": str(cash - reviewed) if method == "CASH" else "0"}
        return {"url": mobile_url("receipt", invoice=invoice.pk), "message": "Đã thu đủ tiền và chốt hóa đơn."}
