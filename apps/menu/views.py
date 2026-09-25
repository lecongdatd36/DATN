from django.contrib import messages
from django.contrib.auth.mixins import AccessMixin
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.generic import DetailView, FormView, ListView

from core.forms import add_service_errors, filter_query_string
from .forms import CategoryForm, UnitForm, DishForm, AvailabilityForm, CatalogFilterForm, DishFilterForm
from .models import Category, Unit, Dish, MenuActivityLog
from .permissions import has_menu_permission
from .selectors import catalog_entries, dishes
from .services import save_catalog, save_dish, change_availability


@method_decorator(never_cache, name="dispatch")
class MenuPermissionMixin(AccessMixin):
    menu_permission = "manage_menu"
    permission_denied_message = "Bạn không có quyền sử dụng chức năng này."

    def dispatch(self, request, *args, **kwargs):
        if not has_menu_permission(request.user, self.menu_permission):
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)


class DishListView(MenuPermissionMixin, ListView):
    menu_permission = "view_dish"
    template_name = "menu/dish_list.html"
    paginate_by = 20

    def get_queryset(self):
        self.filter_form = DishFilterForm(self.request.GET)
        return dishes(**self.filter_form.cleaned_data) if self.filter_form.is_valid() else Dish.objects.none()

    def get_context_data(self, **kwargs):
        return super().get_context_data(filter_form=self.filter_form, query_string=filter_query_string(self.request.GET), **kwargs)


class DishDetailView(MenuPermissionMixin, DetailView):
    menu_permission = "view_dish"
    template_name = "menu/detail.html"
    context_object_name = "dish"
    queryset = Dish.objects.select_related("category", "unit")


class CatalogListView(MenuPermissionMixin, ListView):
    template_name = "menu/catalog_list.html"
    paginate_by = 20
    kind = "category"
    model = Category
    entity_label = "Nhóm món"

    def get_queryset(self):
        self.filter_form = CatalogFilterForm(self.request.GET)
        return catalog_entries(self.model, **self.filter_form.cleaned_data) if self.filter_form.is_valid() else self.model.objects.none()

    def get_context_data(self, **kwargs):
        return super().get_context_data(filter_form=self.filter_form, query_string=filter_query_string(self.request.GET),
            entity_label=self.entity_label, create_route=f"menu:{self.kind}_create", update_route=f"menu:{self.kind}_update", **kwargs)


class UnitListView(CatalogListView):
    kind = "unit"
    model = Unit
    entity_label = "Đơn vị tính"


class CatalogFormView(MenuPermissionMixin, FormView):
    template_name = "menu/form.html"
    form_class = CategoryForm
    model = Category
    kind = "category"
    entity_label = "nhóm món"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        self.object = get_object_or_404(self.model, pk=self.kwargs["pk"]) if "pk" in self.kwargs else None
        kwargs["instance"] = self.object
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(object=self.object, entity_label=self.entity_label, list_url=reverse(f"menu:{self.kind}_list"))
        return context

    def save(self, data):
        return save_catalog(actor=self.request.user, kind=self.kind, object_id=self.object.pk if self.object else None, **data)

    def form_valid(self, form):
        try:
            obj = self.save(form.cleaned_data)
        except ValidationError as error:
            add_service_errors(form, error)
            return self.form_invalid(form)
        except self.model.DoesNotExist as error:
            raise Http404("Dữ liệu không còn tồn tại.") from error
        messages.success(self.request, f"Đã lưu {self.entity_label}.")
        return HttpResponseRedirect(obj.get_absolute_url() if isinstance(obj, Dish) else reverse(f"menu:{self.kind}_list"))


class UnitFormView(CatalogFormView):
    form_class = UnitForm
    model = Unit
    kind = "unit"
    entity_label = "đơn vị tính"


class DishFormView(CatalogFormView):
    form_class = DishForm
    model = Dish
    kind = "dish"
    entity_label = "món"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        self.saved_image_url = self.object.thumbnail.url if self.object and self.object.thumbnail else ""
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["saved_image_url"] = self.saved_image_url
        return context

    def save(self, data):
        data = data.copy()
        data["category_id"] = data.pop("category").pk
        data["unit_id"] = data.pop("unit").pk
        if data.get("image") is not False and "image" not in self.request.FILES:
            data["image"] = None
        return save_dish(actor=self.request.user, dish_id=self.object.pk if self.object else None, **data)


class AvailabilityView(MenuPermissionMixin, FormView):
    menu_permission = "change_availability"
    template_name = "menu/availability.html"
    form_class = AvailabilityForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        self.dish = get_object_or_404(Dish.objects.select_related("category", "unit"), pk=self.kwargs["pk"])
        kwargs["initial"] = {"status": self.dish.status, "expected_revision": self.dish.revision}
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["dish"] = self.dish
        return context

    def form_valid(self, form):
        try:
            change_availability(actor=self.request.user, dish_id=self.dish.pk, **form.cleaned_data)
        except ValidationError as error:
            add_service_errors(form, error)
            return self.form_invalid(form)
        except Dish.DoesNotExist as error:
            raise Http404("Món không còn tồn tại.") from error
        messages.success(self.request, "Đã cập nhật trạng thái phục vụ.")
        return HttpResponseRedirect(self.dish.get_absolute_url())


class MenuLogView(MenuPermissionMixin, ListView):
    menu_permission = "view_menuactivitylog"
    template_name = "menu/logs.html"
    model = MenuActivityLog
    paginate_by = 20
