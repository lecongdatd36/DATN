from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse, reverse_lazy
from django.views.generic import DetailView, FormView, ListView, UpdateView
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters

from core.mixins import ManagerRequiredMixin
from core.forms import add_service_errors, filter_query_string
from apps.accounts.permissions import can_manage_target

from .forms import EmployeeFilterForm, EmployeeForm, EmployeeStatusForm
from .models import EmployeeActivityLog, EmployeeProfile
from .selectors import employee_list
from .services import change_employee_status, delete_employee, update_employee


@method_decorator(never_cache, name="dispatch")
class EmployeeListView(ManagerRequiredMixin, ListView):
    template_name = "employees/employee_list.html"
    paginate_by = 20

    def get_queryset(self):
        self.filter_form = EmployeeFilterForm(self.request.GET)
        if not self.filter_form.is_valid():
            return EmployeeProfile.objects.none()
        filters = self.filter_form.cleaned_data
        return employee_list(
            query=filters["q"],
            position=filters["position"],
            status=filters["status"],
            account_status=filters["account_status"],
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filter_form"] = self.filter_form
        context["query_string"] = filter_query_string(self.request.GET)
        for employee in context["page_obj"]:
            employee.can_manage = can_manage_target(self.request.user, employee.user)
        return context


class EmployeeCreateView(ManagerRequiredMixin, FormView):
    http_method_names = ["get", "head", "options"]

    def get(self, request, *args, **kwargs):
        return HttpResponseRedirect(f"{reverse('accounts:account_create')}?type=EMPLOYEE")


@method_decorator(never_cache, name="dispatch")
class EmployeeDetailView(ManagerRequiredMixin, DetailView):
    model = EmployeeProfile
    template_name = "employees/employee_detail.html"
    context_object_name = "employee"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["activity_logs"] = EmployeeActivityLog.objects.filter(employee=self.object).select_related("performed_by")
        context["can_edit_employee"] = can_manage_target(self.request.user, self.object.user)
        return context


class ManagedEmployeeMixin:
    """Kiểm tra đối tượng sau xác thực và trước khi hiển thị form."""
    def dispatch(self, request, *args, **kwargs):
        self.employee = get_object_or_404(EmployeeProfile.objects.select_related("user", "job_position"), pk=kwargs["pk"])
        if not can_manage_target(request.user, self.employee.user):
            raise PermissionDenied("Bạn không được sửa hồ sơ nhân viên này.")
        return super().dispatch(request, *args, **kwargs)


@method_decorator(never_cache, name="dispatch")
class EmployeeStatusView(ManagerRequiredMixin, ManagedEmployeeMixin, FormView):
    template_name = "employees/employee_status_form.html"
    form_class = EmployeeStatusForm
    success_url = reverse_lazy("employees:employee_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["employee"] = self.employee
        return context

    def get_initial(self):
        return {"status": self.employee.employment_status, "resignation_date": self.employee.resignation_date}

    def form_valid(self, form):
        try:
            employee = change_employee_status(
                actor=self.request.user,
                employee_id=self.employee.pk,
                status=form.cleaned_data["status"],
                resignation_date=form.cleaned_data.get("resignation_date"),
            )
        except ValidationError as error:
            add_service_errors(form, error)
            return self.form_invalid(form)
        except EmployeeProfile.DoesNotExist as error:
            raise Http404("Nhân viên không còn tồn tại.") from error
        messages.success(self.request, f"Đã cập nhật trạng thái nhân viên {employee.full_name}.")
        return super().form_valid(form)


@method_decorator(never_cache, name="dispatch")
class EmployeeDeleteView(ManagerRequiredMixin, ManagedEmployeeMixin, FormView):
    template_name = "employees/employee_delete.html"
    form_class = forms.Form
    success_url = reverse_lazy("employees:employee_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["employee"] = self.employee
        return context

    def form_valid(self, form):
        try:
            delete_employee(actor=self.request.user, employee_id=self.employee.pk)
        except ValidationError as error:
            add_service_errors(form, error)
            return self.form_invalid(form)
        except EmployeeProfile.DoesNotExist as error:
            raise Http404("Nhân viên không còn tồn tại.") from error
        messages.success(self.request, "Đã xóa nhân viên và tài khoản liên kết.")
        return super().form_valid(form)


@method_decorator(never_cache, name="dispatch")
@method_decorator(sensitive_post_parameters("password1", "password2"), name="dispatch")
class EmployeeUpdateView(ManagerRequiredMixin, ManagedEmployeeMixin, UpdateView):
    model = EmployeeProfile
    form_class = EmployeeForm
    template_name = "employees/employee_form.html"
    success_url = reverse_lazy("employees:employee_list")

    def get_object(self, queryset=None):
        return self.employee

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.object.user
        return kwargs

    def form_valid(self, form):
        try:
            self.object = update_employee(
                actor=self.request.user,
                employee_id=self.object.pk,
                user_data={"username": form.cleaned_data["username"], "email": form.cleaned_data["email"]},
                profile_data={name: form.cleaned_data[name] for name in form.Meta.fields},
                password=form.cleaned_data.get("password1"),
            )
        except ValidationError as error:
            add_service_errors(form, error)
            return self.form_invalid(form)
        except EmployeeProfile.DoesNotExist as error:
            raise Http404("Nhân viên không còn tồn tại.") from error
        messages.success(self.request, f"Đã cập nhật nhân viên {self.object.full_name}.")
        return HttpResponseRedirect(self.get_success_url())
