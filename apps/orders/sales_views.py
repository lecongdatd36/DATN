from django.contrib import messages
from django.contrib.auth.mixins import AccessMixin
from django.core.exceptions import PermissionDenied, ValidationError
from decimal import Decimal

from django.db import transaction
from django.db.models import OuterRef, Prefetch, Subquery
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from apps.customers.models import Customer
from apps.customers.services import create_customer
from apps.customers.validators import normalize_phone
from apps.menu.models import Category, Dish
from apps.seating.models import Area, DiningTable
from core.permissions import can_manage_accounts
from .models import Invoice, Order, OrderItem, PaymentRequest
from .permissions import has_order_permission
from . import services


def _error_text(error):
    if hasattr(error, "message_dict"):
        return " ".join(message for values in error.message_dict.values() for message in values)
    return " ".join(error.messages)


class SalesAccessMixin(AccessMixin):
    permission = "view_order"

    def dispatch(self, request, *args, **kwargs):
        if not has_order_permission(request.user, self.permission):
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)


class SalesWorkspaceView(SalesAccessMixin, TemplateView):
    template_name = "staff/sales/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        table_orders = Order.objects.filter(table_id=OuterRef("pk")).order_by("-opened_at", "-pk")
        active_table_orders = table_orders.exclude(status__in=(Order.Status.COMPLETED, Order.Status.CANCELLED))
        tables = DiningTable.objects.select_related("area").filter(
            is_active=True, area__is_active=True
        ).annotate(
            active_order_id=Subquery(active_table_orders.values("pk")[:1]),
            latest_order_id=Subquery(table_orders.values("pk")[:1]),
        )
        selected_order = None
        order_id = self.request.GET.get("order")
        table_id = self.request.GET.get("table")
        active_orders = Order.objects.exclude(status__in=(Order.Status.COMPLETED, Order.Status.CANCELLED)).select_related(
            "table__area", "customer__membership_tier", "employee__user"
        ).prefetch_related("items", "payment_requests")
        if order_id:
            selected_order = active_orders.filter(pk=order_id).first()
        elif table_id:
            selected_order = active_orders.filter(table_id=table_id).order_by("-opened_at", "-pk").first()
        if selected_order:
            preview = services.payment_preview(selected_order)
            selected_order.payment_subtotal = preview["subtotal"]
            selected_order.payment_tier = preview["tier"]
            selected_order.payment_discount_percent = preview["discount_percent"]
            selected_order.payment_discount = preview["discount"]
            selected_order.payment_due = preview["due"]
            live_items = [item for item in selected_order.items.all() if item.status != OrderItem.Status.CANCELLED]
            context["selected_has_drafts"] = any(item.status == OrderItem.Status.DRAFT for item in live_items)
            context["selected_can_request_payment"] = bool(live_items) and all(
                item.status == OrderItem.Status.SERVED for item in live_items
            )
        context.update(
            areas=Area.objects.filter(is_active=True).prefetch_related(Prefetch("tables", queryset=tables)),
            tables=tables,
            categories=Category.objects.filter(is_active=True),
            dishes=Dish.objects.filter(status=Dish.Status.AVAILABLE, category__is_active=True, unit__is_active=True).select_related("category", "unit"),
            selected_order=selected_order,
            active_orders=active_orders,
            customers=Customer.objects.order_by("-created_at")[:30],
            payment_requests=PaymentRequest.objects.filter(status=PaymentRequest.Status.WAITING).select_related("order__table"),
            can_manage_order=has_order_permission(self.request.user, "manage_order"),
            can_collect_payment=has_order_permission(self.request.user, "collect_payment"),
            is_manager=can_manage_accounts(self.request.user),
            available_tables=DiningTable.objects.filter(status=DiningTable.Status.AVAILABLE, is_active=True, area__is_active=True).exclude(pk=selected_order.table_id if selected_order else None),
        )
        return context


class SalesStateView(SalesAccessMixin, View):
    def get(self, request):
        tables = list(DiningTable.objects.filter(is_active=True).values("id", "code", "name", "status", "updated_at"))
        ready = list(OrderItem.objects.filter(status=OrderItem.Status.READY).values("id", "order_id", "dish_name", "quantity", "ready_at"))
        requests = list(PaymentRequest.objects.filter(status=PaymentRequest.Status.WAITING).values("id", "order_id", "requested_at"))
        return JsonResponse({"tables": tables, "ready": ready, "payment_requests": requests})


class CustomerLookupView(SalesAccessMixin, View):
    def get(self, request):
        try:
            phone = normalize_phone(request.GET.get("phone", ""))
        except ValidationError as error:
            return JsonResponse({"ok": False, "error": _error_text(error)}, status=400)
        customer = Customer.objects.select_related("membership_tier").filter(phone=phone).first()
        if customer is None:
            return JsonResponse({"ok": True, "found": False, "phone": phone})
        tier = customer.membership_tier
        return JsonResponse({
            "ok": True,
            "found": True,
            "customer": {
                "id": customer.pk,
                "name": customer.full_name,
                "phone": customer.phone,
                "tier": tier.name if tier else "Chưa có hạng",
                "discount_percent": str(tier.discount_percent if tier else Decimal("0")),
                "total_spending": str(customer.total_spending),
            },
        })


class EstimatePrintView(SalesAccessMixin, TemplateView):
    template_name = "staff/sales/print_bill.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order = get_object_or_404(
            Order.objects.select_related("table__area", "customer__membership_tier", "employee__user").prefetch_related("items"),
            pk=self.kwargs["order_id"],
        )
        if order.status in (Order.Status.COMPLETED, Order.Status.CANCELLED):
            raise PermissionDenied("Đơn đã kết thúc, không thể in phiếu tạm tính.")
        context.update(order=order, preview=services.payment_preview(order), document_type="estimate")
        return context


class InvoicePrintView(SalesAccessMixin, TemplateView):
    permission = "collect_payment"
    template_name = "staff/sales/print_bill.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        invoice = get_object_or_404(
            Invoice.objects.select_related("order__table__area", "customer__membership_tier").prefetch_related("order__items", "payments"),
            pk=self.kwargs["invoice_id"], status=Invoice.Status.PAID,
        )
        context.update(order=invoice.order, invoice=invoice, document_type="invoice")
        return context


class SalesActionView(SalesAccessMixin, View):
    permission = "manage_order"

    def post(self, request, action):
        try:
            # Customer creation and opening the table must either both succeed
            # or both roll back, preventing orphan customer records.
            with transaction.atomic():
                result = self._perform(request, action)
        except (ValidationError, PermissionDenied, TypeError, ValueError, KeyError) as error:
            messages.error(request, _error_text(error) if isinstance(error, ValidationError) else (str(error) or "Dữ liệu thao tác không hợp lệ."))
            return redirect(request.POST.get("next") or reverse("sales:workspace"))
        messages.success(request, "Đã cập nhật bán hàng.")
        order_id = getattr(result, "order_id", None) or getattr(result, "pk", None)
        if isinstance(result, DiningTable):
            order_id = None
        target = reverse("sales:workspace")
        if order_id:
            target += f"?order={order_id}"
        return redirect(target)

    def _perform(self, request, action):
        if action == "open":
            customer = None
            raw_phone = request.POST.get("customer_phone", "").strip()
            if raw_phone:
                phone = normalize_phone(raw_phone)
                customer = Customer.objects.filter(phone=phone).first()
                if customer is None:
                    customer_name = request.POST.get("customer_name", "").strip()
                    if not customer_name:
                        raise ValidationError({"customer_name": "Số điện thoại chưa có trong hệ thống. Vui lòng nhập tên khách mới."})
                    customer = create_customer(actor=request.user, full_name=customer_name, phone=phone)
            return services.open_table(
                actor=request.user,
                table_id=int(request.POST["table_id"]),
                guest_count=int(request.POST["guest_count"]),
                customer_id=customer.pk if customer else None,
                reservation_id=int(request.POST["reservation_id"]) if request.POST.get("reservation_id") else None,
                note=request.POST.get("note", ""),
            )
        order_id = int(request.POST["order_id"])
        order = get_object_or_404(Order, pk=order_id)
        revision = int(request.POST.get("expected_revision", order.revision))
        if action == "add":
            return services.add_item(actor=request.user, order_id=order_id, expected_revision=revision, dish_id=int(request.POST["dish_id"]), quantity=int(request.POST.get("quantity", 1)), note=request.POST.get("note", ""))
        if action == "update-item":
            return services.edit_item(actor=request.user, order_id=order_id, item_id=int(request.POST["item_id"]), expected_revision=revision, quantity=int(request.POST["quantity"]), note=request.POST.get("note", ""))
        if action == "remove-item":
            return services.remove_draft_item(actor=request.user, order_id=order_id, item_id=int(request.POST["item_id"]), expected_revision=revision)
        if action == "send":
            return services.send_to_kitchen(actor=request.user, order_id=order_id, expected_revision=revision)
        if action == "served":
            return services.transition_item(actor=request.user, order_id=order_id, item_id=int(request.POST["item_id"]), expected_revision=revision, target=OrderItem.Status.SERVED)
        if action == "request-payment":
            return services.request_payment(actor=request.user, order_id=order_id, expected_revision=revision, note=request.POST.get("note", ""))
        if action == "move":
            return services.move_table(actor=request.user, order_id=order_id, target_table_id=int(request.POST["target_table_id"]))
        raise ValidationError("Thao tác bán hàng không hợp lệ.")


class PaymentActionView(SalesAccessMixin, View):
    permission = "collect_payment"

    def post(self, request):
        order_id = request.POST.get("order_id", "")
        try:
            invoice = services.process_payment(
                actor=request.user,
                order_id=int(order_id),
                payment_method=request.POST.get("payment_method", "CASH"),
                transaction_code=request.POST.get("transaction_code", ""),
            )
        except (ValidationError, Order.DoesNotExist, TypeError, ValueError) as error:
            message = _error_text(error) if isinstance(error, ValidationError) else "Đơn hàng không còn tồn tại hoặc dữ liệu thanh toán không hợp lệ."
            messages.error(request, message)
            target = reverse("sales:workspace")
            if str(order_id).isdigit():
                target += f"?order={order_id}"
            return redirect(target)
        else:
            messages.success(request, f"Đã thanh toán hóa đơn {invoice.invoice_code}.")
            if request.POST.get("print_after_payment"):
                return redirect("sales:invoice_print", invoice_id=invoice.pk)
        return redirect("sales:workspace")


class FinishCleaningView(SalesAccessMixin, View):
    permission = "manage_order"

    def post(self, request, table_id):
        try:
            services.finish_cleaning(actor=request.user, table_id=table_id)
        except ValidationError as error:
            messages.error(request, _error_text(error))
        else:
            messages.success(request, "Bàn đã sẵn sàng phục vụ.")
        return redirect("sales:workspace")
