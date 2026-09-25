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
from .forms import OpenOrderForm, WalkInForm, AddItemForm, ItemEditForm, RevisionForm, ReasonForm, OrderFilterForm, KitchenFilterForm
from .models import Order, OrderItem
from .permissions import has_order_permission
from .selectors import order_list, kitchen_items
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
    queryset = Order.objects.select_related("booking__table").prefetch_related(Prefetch("items", queryset=OrderItem.objects.select_related("dish")))
    context_object_name = "order"
    template_name = "orders/detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        items = list(self.object.items.all())
        context["has_drafts"] = any(item.status == "DRAFT" for item in items)
        context["live_items"] = any(item.status != "CANCELLED" for item in items)
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
        return super().get_context_data(title=self.title, back_url=reverse("orders:list"), **kwargs)

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
        return HttpResponseRedirect(order.get_absolute_url())


class WalkInView(OpenOrderView):
    form_class = WalkInForm
    title = "Nhận khách không đặt trước và mở đơn"

    def get_initial(self):
        return {"table": self.request.GET.get("table"), "party_size": 1}

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
        return {"add": AddItemForm, "edit": ItemEditForm, "void": ReasonForm}.get(self.action, RevisionForm)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        self.order = get_object_or_404(Order.objects.select_related("booking__table"), pk=self.kwargs["pk"])
        self.item = get_object_or_404(OrderItem.objects.select_related("dish"), pk=self.kwargs["item_id"], order=self.order) if "item_id" in self.kwargs else None
        kwargs["initial"] = {"expected_revision": self.order.revision, "quantity": self.item.quantity if self.item else 1,
                             "note": self.item.note if self.item else ""}
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(order=self.order, item=self.item, title=self.titles[self.action], back_url=self.order.get_absolute_url(), action=self.action)
        if self.action == "send" and self.item is None:
            context["draft_items"] = self.order.items.filter(status=OrderItem.Status.DRAFT)
        return context

    def save(self, data):
        base = dict(actor=self.request.user, order_id=self.order.pk, **data)
        if self.action == "add":
            base["dish_id"] = base.pop("dish").pk
            services.add_item(**base)
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
