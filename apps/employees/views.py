from urllib.parse import urlencode

from django import forms
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DetailView, FormView, ListView, UpdateView

from core.mixins import ManagerRequiredMixin

from .forms import EmployeeFilterForm, EmployeeForm, EmployeeStatusForm
from .models import EmployeeActivityLog, EmployeeProfile
from .selectors import employee_list
from .services import change_employee_status, create_employee, delete_employee, update_employee


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
        context["query_string"] = urlencode({key: value for key, value in self.filter_form.cleaned_data.items() if value})
        return context


class EmployeeCreateView(ManagerRequiredMixin, CreateView):
    def dispatch(self, request, *args, **kwargs):
        return HttpResponseRedirect(f"{reverse('accounts:account_create')}?type=EMPLOYEE")

    template_name = "employees/employee_form.html"
    form_class = EmployeeForm
    success_url = reverse_lazy("employees:employee_list")

    def form_valid(self, form):
        try:
            self.object = create_employee(
                actor=self.request.user,
                user_data={"username": form.cleaned_data["username"], "email": form.cleaned_data["email"]},
                profile_data={name: form.cleaned_data[name] for name in form.Meta.fields},
                password=form.cleaned_data["password1"],
            )
        except ValidationError as error:
            form.add_error(None, error)
            return self.form_invalid(form)
        messages.success(self.request, f"Đã tạo nhân viên {self.object.full_name}.")
        return HttpResponseRedirect(self.get_success_url())


class EmployeeDetailView(ManagerRequiredMixin, DetailView):
    model = EmployeeProfile
    template_name = "employees/employee_detail.html"
    context_object_name = "employee"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["activity_logs"] = EmployeeActivityLog.objects.filter(employee=self.object).select_related("performed_by")
        return context


class EmployeeStatusView(ManagerRequiredMixin, FormView):
    template_name = "employees/employee_status_form.html"
    form_class = EmployeeStatusForm
    success_url = reverse_lazy("employees:employee_list")

    def dispatch(self, request, *args, **kwargs):
        self.employee = get_object_or_404(EmployeeProfile, pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["employee"] = self.employee
        return context

    def get_initial(self):
        return {"status": self.employee.employment_status}

    def form_valid(self, form):
        try:
            employee = change_employee_status(
                actor=self.request.user,
                employee_id=self.employee.pk,
                status=form.cleaned_data["status"],
                resignation_date=form.cleaned_data.get("resignation_date"),
            )
        except (ValidationError, ValueError) as error:
            form.add_error("status", error)
            return self.form_invalid(form)
        messages.success(self.request, f"Đã cập nhật trạng thái nhân viên {employee.full_name}.")
        return super().form_valid(form)


class EmployeeDeleteView(ManagerRequiredMixin, FormView):
    template_name = "employees/employee_delete.html"
    form_class = forms.Form
    success_url = reverse_lazy("employees:employee_list")

    def dispatch(self, request, *args, **kwargs):
        self.employee = get_object_or_404(EmployeeProfile, pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["employee"] = self.employee
        return context

    def form_valid(self, form):
        try:
            delete_employee(actor=self.request.user, employee_id=self.employee.pk)
        except PermissionDenied as error:
            form.add_error(None, error)
            return self.form_invalid(form)
        messages.success(self.request, "Đã xóa nhân viên và tài khoản liên kết.")
        return super().form_valid(form)


class EmployeeUpdateView(ManagerRequiredMixin, UpdateView):
    model = EmployeeProfile
    form_class = EmployeeForm
    template_name = "employees/employee_form.html"
    success_url = reverse_lazy("employees:employee_list")

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
            form.add_error(None, error)
            return self.form_invalid(form)
        messages.success(self.request, f"Đã cập nhật nhân viên {self.object.full_name}.")
        return HttpResponseRedirect(self.get_success_url())
