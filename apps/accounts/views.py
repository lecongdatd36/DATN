"""Xử lý request/response; nghiệp vụ quản lý tài khoản nằm trong services."""

from urllib.parse import urlencode

from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth import views as auth_views
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.functional import cached_property
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.generic import FormView, ListView, TemplateView

from core.mixins import ManagerRequiredMixin

from .forms import (
    AccountFilterForm,
    EmployeePasswordResetForm,
    LoginForm,
    PasswordChangeForm,
)
from .permissions import can_manage_target
from .selectors import account_list
from .services import change_own_password, reset_employee_password, set_account_active

User = get_user_model()


class LoginView(auth_views.LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True


class LogoutView(auth_views.LogoutView):
    """Django 5.2 chỉ cho đăng xuất bằng POST có CSRF."""

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        messages.success(request, "Bạn đã đăng xuất.")
        return response


@method_decorator(never_cache, name="dispatch")
class WorkspaceView(LoginRequiredMixin, TemplateView):
    template_name = "accounts/workspace.html"


class PasswordChangeView(auth_views.PasswordChangeView):
    http_method_names = ["get", "post", "head", "options"]
    form_class = PasswordChangeForm
    template_name = "accounts/password_change_form.html"
    success_url = reverse_lazy("accounts:password_change_done")

    def form_valid(self, form):
        try:
            user = change_own_password(
                actor=self.request.user,
                old_password=form.cleaned_data["old_password"],
                new_password=form.cleaned_data["new_password1"],
            )
        except ValidationError as error:
            form.add_error(None, error)
            return self.form_invalid(form)
        update_session_auth_hash(self.request, user)
        messages.success(self.request, "Đổi mật khẩu thành công.")
        return HttpResponseRedirect(self.get_success_url())


class PasswordChangeDoneView(auth_views.PasswordChangeDoneView):
    template_name = "accounts/password_change_done.html"


@method_decorator(never_cache, name="dispatch")
class AccountListView(ManagerRequiredMixin, ListView):
    template_name = "accounts/account_list.html"
    paginate_by = 20

    def get_queryset(self):
        self.filter_form = AccountFilterForm(self.request.GET)
        if not self.filter_form.is_valid():
            return User.objects.none()
        return account_list(
            query=self.filter_form.cleaned_data["q"],
            status=self.filter_form.cleaned_data["status"],
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        for account in context["page_obj"]:
            account.can_manage = can_manage_target(self.request.user, account)
        context["filter_form"] = self.filter_form
        context["query_string"] = urlencode(
            {
                key: value
                for key, value in self.filter_form.cleaned_data.items()
                if key in {"q", "status"} and value
            }
        )
        return context


class EmployeeTargetMixin:
    """Kiểm tra đối tượng cả lúc mở form lẫn lúc gửi thay đổi."""

    @cached_property
    def target_user(self):
        target = get_object_or_404(User, pk=self.kwargs["pk"])
        if not can_manage_target(self.request.user, target):
            raise PermissionDenied("Bạn không được quản lý tài khoản này.")
        return target

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["target_user"] = self.target_user
        return context


@method_decorator(never_cache, name="dispatch")
class AccountStatusView(ManagerRequiredMixin, EmployeeTargetMixin, FormView):
    http_method_names = ["get", "post", "head", "options"]
    template_name = "accounts/account_confirm_status.html"
    form_class = forms.Form
    success_url = reverse_lazy("accounts:account_list")
    activate = False

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["action"] = "unlock" if self.activate else "lock"
        return context

    def form_valid(self, form):
        try:
            target = set_account_active(
                actor=self.request.user,
                target_id=self.target_user.pk,
                is_active=self.activate,
            )
        except User.DoesNotExist as error:
            raise Http404("Tài khoản không còn tồn tại.") from error
        verb = "mở khóa" if self.activate else "khóa"
        messages.success(self.request, f"Đã {verb} tài khoản {target.username}.")
        return super().form_valid(form)


@method_decorator(never_cache, name="dispatch")
@method_decorator(sensitive_post_parameters("new_password1", "new_password2"), name="dispatch")
class EmployeePasswordResetView(ManagerRequiredMixin, EmployeeTargetMixin, FormView):
    http_method_names = ["get", "post", "head", "options"]
    template_name = "accounts/account_password_reset.html"
    form_class = EmployeePasswordResetForm
    success_url = reverse_lazy("accounts:account_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.target_user
        return kwargs

    def form_valid(self, form):
        try:
            target = reset_employee_password(
                actor=self.request.user,
                target_id=self.target_user.pk,
                password=form.cleaned_data["new_password1"],
            )
        except User.DoesNotExist as error:
            raise Http404("Tài khoản không còn tồn tại.") from error
        except ValidationError as error:
            form.add_error(None, error)
            return self.form_invalid(form)
        messages.success(self.request, f"Đã đặt lại mật khẩu cho {target.username}.")
        return super().form_valid(form)
