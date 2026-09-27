from django.contrib import messages
from django.contrib.auth.mixins import AccessMixin
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Prefetch
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.generic import DetailView, FormView, ListView

from core.forms import add_service_errors, filter_query_string
from apps.bookings.models import Booking
from apps.menu.models import Dish
from .forms import OpenOrderForm, WalkInForm, AddItemForm, BulkAddItemsForm, ItemEditForm, RevisionForm, ReasonForm, PaymentForm, TablePaymentForm, OrderFilterForm, KitchenFilterForm
from .models import Order, OrderItem, Payment
from .permissions import has_order_permission
from .selectors import order_list, kitchen_items, payable_table_orders, payment_areas
from . import services


@method_decorator(never_cache, name="dispatch")
class OrderPermissionMixin(AccessMixin):
    order_permission = "manage_order"

    def dispatch(self, request, *args, **kwargs):
        if not has_order_permission(request.user, self.order_permission):
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)


class OrderListView(OrderPermissionMixin, ListView):
    order_permission = "view_order"
    template_name = "orders/list.html"
    paginate_by = 20

    def get_queryset(self):
        self.filter_form = OrderFilterForm(self.request.GET)
        return order_list(**self.filter_form.cleaned_data) if self.filter_form.is_valid() else Order.objects.none()

    def get_context_data(self, **kwargs):
        return super().get_context_data(filter_form=self.filter_form, query_string=filter_query_string(self.request.GET), **kwargs)


class OrderDetailView(OrderPermissionMixin, DetailView):
    order_permission = "view_order"
    queryset = Order.objects.select_related("booking__table", "invoice").prefetch_related(
        Prefetch("items", queryset=OrderItem.objects.select_related("dish")),
        Prefetch("invoice__payments", queryset=Payment.objects.select_related("batch")),
    )
    context_object_name = "order"
    template_name = "orders/detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        items = list(self.object.items.all())
        context["has_drafts"] = any(item.status == "DRAFT" for item in items)
        context["live_items"] = any(item.status != "CANCELLED" for item in items)
        context["invoice"] = getattr(self.object, "invoice", None)
        if context["invoice"] is not None:
            context["invoice_remaining"] = context["invoice"].remaining
        else:
            context["invoice_remaining"] = self.object.total
        context["can_reopen_order"] = context["invoice"] is None or context["invoice"].paid_amount == 0
        if has_order_permission(self.request.user, "view_orderactivitylog"):
            context["log_page"] = Paginator(self.object.activity_logs.all(), 20).get_page(self.request.GET.get("page"))
        return context


class OpenOrderView(OrderPermissionMixin, FormView):
    form_class = OpenOrderForm
    template_name = "orders/form.html"
    title = "Mở đơn cho khách đã nhận bàn"

    def get_initial(self):
        return {"booking": self.request.GET.get("booking")}

    def get_context_data(self, **kwargs):
        return super().get_context_data(title=self.title, back_url=reverse("orders:list"), submit_label="Mở đơn & chọn món", **kwargs)

    def save(self, data):
        return services.open_order(actor=self.request.user, booking_id=data["booking"].pk)

    def form_valid(self, form):
        try:
            order = self.save(form.cleaned_data)
        except ValidationError as error:
            add_service_errors(form, error)
            return self.form_invalid(form)
        except Booking.DoesNotExist as error:
            raise Http404("Lượt khách không còn tồn tại.") from error
        if order.status == Order.Status.OPEN:
            return HttpResponseRedirect(reverse("orders:add_item", args=[order.pk]))
        return HttpResponseRedirect(order.get_absolute_url())


class WalkInView(OpenOrderView):
    form_class = WalkInForm
    title = "Nhận khách không đặt trước và mở đơn"

    def get_initial(self):
        return {"table": self.request.GET.get("table"), "party_size": 1}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["submit_label"] = "Nhận khách & chọn món"
        return context

    def save(self, data):
        data = data.copy()
        data["table_id"] = data.pop("table").pk
        return services.open_walk_in_order(actor=self.request.user, **data)


class OrderActionView(OrderPermissionMixin, FormView):
    template_name = "orders/form.html"
    form_class = RevisionForm
    action = "send"
    titles = {"add": "Thêm món", "edit": "Sửa món chưa gửi Bếp", "send": "Gửi các món chưa gửi xuống Bếp",
              "await": "Chuyển đơn sang chờ thanh toán", "reopen": "Tiếp tục gọi món", "void": "Hủy đơn"}

    def get_form_class(self):
        return {"add": BulkAddItemsForm, "edit": ItemEditForm, "void": ReasonForm}.get(self.action, RevisionForm)

    def get_template_names(self):
        return ["orders/add_items.html"] if self.action == "add" else [self.template_name]

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        self.order = get_object_or_404(
            Order.objects.select_related("booking__table").prefetch_related("items"),
            pk=self.kwargs["pk"],
        )
        self.item = get_object_or_404(OrderItem.objects.select_related("dish"), pk=self.kwargs["item_id"], order=self.order) if "item_id" in self.kwargs else None
        kwargs["initial"] = {"expected_revision": self.order.revision, "quantity": self.item.quantity if self.item else 1,
                             "note": self.item.note if self.item else ""}
        if self.action == "add":
            self.menu_dishes = list(
                Dish.objects.filter(
                    status=Dish.Status.AVAILABLE,
                    category__is_active=True,
                    unit__is_active=True,
                ).select_related("category", "unit").order_by("category__name", "name", "pk")
            )
            kwargs["dishes_queryset"] = Dish.objects.filter(pk__in=[dish.pk for dish in self.menu_dishes])
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(order=self.order, item=self.item, title=self.titles[self.action], back_url=self.order.get_absolute_url(), action=self.action)
        if self.action == "add":
            selected_ids = set(self.request.POST.getlist("dishes"))
            for dish in self.menu_dishes:
                dish.order_selected = str(dish.pk) in selected_ids
                dish.order_quantity = self.request.POST.get(f"quantity_{dish.pk}", "1")
                dish.order_note = self.request.POST.get(f"note_{dish.pk}", "")
            context["menu_dishes"] = self.menu_dishes
            context["menu_categories"] = list(dict.fromkeys(dish.category for dish in self.menu_dishes))
            context["existing_items"] = [
                item for item in self.order.items.all()
                if item.status != OrderItem.Status.CANCELLED
            ]
            context["existing_order_total"] = self.order.total
        if self.action == "send" and self.item is None:
            context["draft_items"] = self.order.items.filter(status=OrderItem.Status.DRAFT)
        return context

    def save(self, data):
        base = dict(actor=self.request.user, order_id=self.order.pk, **data)
        if self.action == "add":
            base.pop("dishes", None)
            services.add_items(**base)
        elif self.action == "edit":
            services.edit_item(item_id=self.item.pk, **base)
        elif self.action == "send":
            services.send_to_kitchen(**base)
        else:
            services.change_order_status(target={"await": "AWAITING_PAYMENT", "reopen": "OPEN", "void": "VOID"}[self.action], **base)

    def form_valid(self, form):
        try:
            self.save(form.cleaned_data)
        except ValidationError as error:
            add_service_errors(form, error)
            return self.form_invalid(form)
        except (Order.DoesNotExist, OrderItem.DoesNotExist) as error:
            raise Http404("Đơn hoặc món không còn tồn tại.") from error
        messages.success(self.request, "Đã cập nhật đơn hàng.")
        return HttpResponseRedirect(self.order.get_absolute_url())


class OrderPaymentView(OrderPermissionMixin, FormView):
    order_permission = "collect_payment"
    form_class = PaymentForm
    template_name = "orders/form.html"
    title = "Thu tiền"

    def dispatch(self, request, *args, **kwargs):
        self.order = get_object_or_404(Order.objects.select_related("booking__table", "invoice"), pk=kwargs["pk"])
        if self.order.status != Order.Status.AWAITING_PAYMENT:
            raise Http404("Đơn không ở trạng thái chờ thanh toán.")
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        invoice = getattr(self.order, "invoice", None)
        remaining = invoice.remaining if invoice else self.order.total
        kwargs["initial"] = {"expected_revision": self.order.revision, "amount": remaining, "payment_method": "CASH"}
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        invoice = getattr(self.order, "invoice", None)
        remaining = invoice.remaining if invoice else self.order.total
        context.update(order=self.order, title=self.title, back_url=self.order.get_absolute_url(), remaining=remaining, action="payment")
        return context

    def save(self, data):
        return services.record_payment(actor=self.request.user, order_id=self.order.pk, expected_revision=data["expected_revision"],
            amount=data["amount"], payment_method=data["payment_method"], reference=data["reference"])

    def form_valid(self, form):
        try:
            self.save(form.cleaned_data)
        except ValidationError as error:
            add_service_errors(form, error)
            return self.form_invalid(form)
        messages.success(self.request, "Đã ghi nhận thanh toán.")
        return HttpResponseRedirect(self.order.get_absolute_url())


class TablePaymentView(OrderPermissionMixin, FormView):
    order_permission = "collect_payment"
    form_class = TablePaymentForm
    template_name = "orders/table_payment.html"

    def get_area_id(self):
        return self.request.POST.get("area") or self.request.GET.get("area") or ""

    def get_ready_orders(self):
        if not hasattr(self, "ready_orders"):
            self.ready_orders = payable_table_orders(area_id=self.get_area_id() or None)
        return self.ready_orders

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        ready_orders = self.get_ready_orders()
        kwargs["order_queryset"] = Order.objects.filter(pk__in=[order.pk for order in ready_orders])
        if self.request.method == "GET":
            kwargs["initial"] = {"payment_method": "CASH"}
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            ready_orders=self.get_ready_orders(),
            areas=payment_areas(),
            selected_area=self.get_area_id(),
            selected_order_ids=self.request.POST.getlist("orders"),
        )
        return context

    def form_valid(self, form):
        try:
            batch, table_codes = services.pay_tables(
                actor=self.request.user,
                order_ids=form.cleaned_data["orders"].values_list("pk", flat=True),
                payment_method=form.cleaned_data["payment_method"],
                reference=form.cleaned_data["reference"],
            )
        except ValidationError as error:
            add_service_errors(form, error)
            if hasattr(self, "ready_orders"):
                del self.ready_orders
            return self.form_invalid(form)
        messages.success(self.request, f"{batch.batch_code}: đã thanh toán và trả {len(table_codes)} bàn ({', '.join(table_codes)}).")
        return HttpResponseRedirect(reverse("seating:table_list"))


class ItemTransitionView(OrderActionView):
    targets = {"COOKING": "Bắt đầu làm món", "READY": "Món đã làm xong", "SERVED": "Xác nhận đã phục vụ", "CANCELLED": "Hủy món"}

    def dispatch(self, request, *args, **kwargs):
        self.target = kwargs["target"]
        if self.target not in self.targets:
            raise Http404("Thao tác không hợp lệ.")
        self.order_permission = "work_kitchen" if self.target in ("COOKING", "READY") else "manage_order"
        return super().dispatch(request, *args, **kwargs)

    def get_form_class(self):
        return ReasonForm if self.target == "CANCELLED" else RevisionForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self.order_permission == "work_kitchen" and self.item.status in (OrderItem.Status.DRAFT, OrderItem.Status.CANCELLED):
            raise Http404("Món chưa gửi Bếp hoặc đã hủy.")
        if self.target == OrderItem.Status.CANCELLED and self.item.status == OrderItem.Status.SERVED:
            raise Http404("Món đã phục vụ không thể hủy.")
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(title=self.targets[self.target], kitchen_action=self.order_permission == "work_kitchen")
        if context["kitchen_action"]:
            context["back_url"] = reverse("orders:kitchen")
        return context

    def save(self, data):
        services.transition_item(actor=self.request.user, order_id=self.order.pk, item_id=self.item.pk, target=self.target, **data)

    def form_valid(self, form):
        response = super().form_valid(form)
        if isinstance(response, HttpResponseRedirect) and self.order_permission == "work_kitchen":
            return HttpResponseRedirect(reverse("orders:kitchen"))
        if (
            isinstance(response, HttpResponseRedirect)
            and self.target == OrderItem.Status.CANCELLED
            and self.request.GET.get("next") == "add"
        ):
            return HttpResponseRedirect(reverse("orders:add_item", args=[self.order.pk]))
        return response


class KitchenView(OrderPermissionMixin, ListView):
    order_permission = "work_kitchen"
    template_name = "orders/kitchen.html"
    paginate_by = 30

    def get_queryset(self):
        self.filter_form = KitchenFilterForm(self.request.GET)
        return kitchen_items(**self.filter_form.cleaned_data) if self.filter_form.is_valid() else OrderItem.objects.none()

    def get_context_data(self, **kwargs):
        return super().get_context_data(filter_form=self.filter_form, query_string=filter_query_string(self.request.GET), checked_at=timezone.now(), **kwargs)
