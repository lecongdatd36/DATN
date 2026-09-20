from django.contrib import messages
from django.contrib.auth.mixins import AccessMixin
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.generic import FormView, ListView

from core.forms import add_service_errors, filter_query_string
from .forms import AreaFilterForm, AreaForm, DiningTableForm, TableFilterForm
from .models import Area, DiningTable, SeatingActivityLog
from .permissions import has_seating_permission
from .selectors import areas, tables
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

    def get_queryset(self):
        self.status_checked_at = timezone.now()
        self.filter_form = self.filter_class(self.request.GET)
        return tables(at=self.status_checked_at, **self.filter_form.cleaned_data) if self.filter_form.is_valid() else self.model.objects.none()

    def get_context_data(self, **kwargs):
        return super().get_context_data(status_checked_at=self.status_checked_at, **kwargs)


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
