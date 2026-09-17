from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from core.mixins import ManagerRequiredMixin

from .forms import EmployeeFilterForm, EmployeeForm
from .models import EmployeeProfile
from .selectors import employee_list
from .services import create_employee, update_employee


class EmployeeListView(ManagerRequiredMixin, ListView):
    template_name = "employees/employee_list.html"
    paginate_by = 20

    def get_queryset(self):
        self.filter_form = EmployeeFilterForm(self.request.GET)
        if not self.filter_form.is_valid():
            return EmployeeProfile.objects.none()
        return employee_list(**self.filter_form.cleaned_data)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filter_form"] = self.filter_form
        context["query_string"] = urlencode({key: value for key, value in self.filter_form.cleaned_data.items() if value})
        return context


class EmployeeCreateView(ManagerRequiredMixin, CreateView):
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
