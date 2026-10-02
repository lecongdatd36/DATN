from django.contrib import messages
from django.contrib.auth.mixins import AccessMixin
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.generic import FormView, ListView, TemplateView

from core.forms import add_service_errors, filter_query_string
from apps.orders.models import Order
from apps.orders import services as order_services
from .forms import AreaFilterForm, AreaForm, DiningTableForm, TableFilterForm
from .models import Area, DiningTable, DiningTableQRToken, SeatingActivityLog
from .qr import qr_data_uri
from .permissions import has_seating_permission
from .selectors import areas, table_status_counts, tables
from .services import save_area, save_table


@method_decorator(never_cache, name="dispatch")
class SeatingPermissionMixin(AccessMixin):
    seating_permission = "manage_seating"
    permission_denied_message = "Bạn không có quyền sử dụng chức năng này."

    def dispatch(self, request, *args, **kwargs):
        if not has_seating_permission(request.user, self.seating_permission):
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)


class AreaListView(SeatingPermissionMixin, ListView):
    seating_permission = "view_area"
    template_name = "seating/area_list.html"
    paginate_by = 20
    filter_class = AreaFilterForm
    model = Area
    selector = staticmethod(areas)

    def get_queryset(self):
        self.filter_form = self.filter_class(self.request.GET)
        return self.selector(**self.filter_form.cleaned_data) if self.filter_form.is_valid() else self.model.objects.none()

    def get_context_data(self, **kwargs):
        return super().get_context_data(filter_form=self.filter_form, query_string=filter_query_string(self.request.GET), **kwargs)


class TableListView(AreaListView):
    seating_permission = "view_diningtable"
    template_name = "seating/table_list.html"
    filter_class = TableFilterForm
    model = DiningTable
    selector = staticmethod(tables)

    def get_template_names(self):
        if self.request.headers.get("X-Table-Refresh") == "1":
            return ["seating/includes/table_results.html"]
        return [self.template_name]

    def paginate_queryset(self, queryset, page_size):
        paginator = self.get_paginator(queryset, page_size, allow_empty_first_page=True)
        page = paginator.get_page(self.request.GET.get("page", 1))
        return paginator, page, page.object_list, page.has_other_pages()

    def get_queryset(self):
        self.status_checked_at = timezone.now()
        self.filter_form = self.filter_class(self.request.GET)
        return tables(at=self.status_checked_at, **self.filter_form.cleaned_data) if self.filter_form.is_valid() else self.model.objects.none()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(status_checked_at=self.status_checked_at, **kwargs)
        context["service_areas"] = Area.objects.filter(is_active=True).order_by("name", "pk")
        context["selected_area_id"] = self.request.GET.get("area", "")
        context["status_counts"] = table_status_counts(at=self.status_checked_at)
        page = context.get("page_obj")
        rows = page.object_list if page is not None else context.get("object_list", [])
        order_ids = [table.current_order_id for table in rows if table.current_order_id]
        current_orders = {
            order.pk: order
            for order in Order.objects.filter(pk__in=order_ids).select_related("customer").prefetch_related("items")
        }
        for table in rows:
            order = current_orders.get(table.current_order_id)
            if order:
                preview = order_services.payment_preview(order)
                table.current_order_subtotal = preview["subtotal"]
                table.current_order_total = preview["due"]
                table.current_order_discount = preview["discount"]
                table.current_order_customer = order.customer.full_name if order.customer else "Khách lẻ"
                table.current_order_tier = preview["tier"].name if preview["tier"] else "Không có hạng"
                table.current_order_discount_percent = preview["discount_percent"]
                table.current_order_membership_discount = preview["membership_discount"]
                table.current_order_promotion = preview["promotion_code"]
                table.current_order_promotion_discount = preview["promotion_discount"]
        context["table_state_signature"] = "|".join(
            f"{table.pk}:{table.current_status}:{table.current_visit_id or 0}:{table.current_visit_revision or 0}:{table.held_booking_revision or 0}:{table.current_order_id or 0}:{table.current_order_status or '-'}:{table.current_order_total}"
            for table in rows
        )
        return context


class TableQRListView(SeatingPermissionMixin, TemplateView):
    seating_permission = "view_diningtable"
    template_name = "seating/table_qr.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cards = []
        for table in DiningTable.objects.select_related("area").filter(is_active=True, area__is_active=True).order_by("area__name", "code"):
            token, _ = DiningTableQRToken.objects.get_or_create(table=table)
            scan_url = self.request.build_absolute_uri(reverse("customer_portal:qr_table", args=[token.token]))
            cards.append({"table": table, "scan_url": scan_url, "qr_image": qr_data_uri(scan_url)})
        context["qr_cards"] = cards
        return context


class AreaFormView(SeatingPermissionMixin, FormView):
    form_class = AreaForm
    model = Area
    template_name = "seating/form.html"
    entity_label = "khu vực"
    list_route = "seating:area_list"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        self.object = get_object_or_404(self.model, pk=self.kwargs["pk"]) if "pk" in self.kwargs else None
        kwargs["instance"] = self.object
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(object=self.object, entity_label=self.entity_label, list_url=reverse(self.list_route))
        return context

    def save(self, data):
        return save_area(actor=self.request.user, area_id=self.object.pk if self.object else None, **data)

    def form_valid(self, form):
        try:
            self.save(form.cleaned_data)
        except ValidationError as error:
            add_service_errors(form, error)
            return self.form_invalid(form)
        except self.model.DoesNotExist as error:
            raise Http404("Dữ liệu không còn tồn tại.") from error
        messages.success(self.request, f"Đã lưu {self.entity_label}.")
        return HttpResponseRedirect(reverse(self.list_route))


class TableFormView(AreaFormView):
    form_class = DiningTableForm
    model = DiningTable
    entity_label = "bàn"
    list_route = "seating:table_list"

    def save(self, data):
        return save_table(
            actor=self.request.user, table_id=self.object.pk if self.object else None,
            code=data["code"], area_id=data["area"].pk, capacity=data["capacity"], is_active=data["is_active"],
        )


class SeatingLogView(SeatingPermissionMixin, ListView):
    seating_permission = "view_seatingactivitylog"
    model = SeatingActivityLog
    template_name = "seating/logs.html"
    paginate_by = 20
