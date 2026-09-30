from django import forms
from django.contrib import messages
from django.contrib.auth.mixins import AccessMixin
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.generic import CreateView, DetailView, FormView, ListView, UpdateView

from core.forms import add_service_errors, filter_query_string
from apps.orders.models import Invoice
from .forms import CustomerFilterForm, CustomerForm, CustomerLogFilterForm, MembershipTierForm
from .models import Customer, CustomerActivityLog, MembershipTier
from .permissions import has_customer_permission
from .selectors import customer_list, customer_logs
from .services import create_customer, delete_customer, recalculate_membership_tiers, update_customer


@method_decorator(never_cache, name="dispatch")
class CustomerPermissionMixin(AccessMixin):
    customer_permission = "view_customer"
    permission_denied_message = "Bạn không có quyền sử dụng chức năng khách hàng này."

    def dispatch(self, request, *args, **kwargs):
        if not has_customer_permission(request.user, self.customer_permission):
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)


class CustomerListView(CustomerPermissionMixin, ListView):
    template_name = "customers/customer_list.html"
    paginate_by = 20

    def get_queryset(self):
        self.filter_form = CustomerFilterForm(self.request.GET)
        return customer_list(query=self.filter_form.cleaned_data["q"]) if self.filter_form.is_valid() else Customer.objects.none()

    def get_context_data(self, **kwargs):
        return super().get_context_data(
            filter_form=self.filter_form, query_string=filter_query_string(self.request.GET), **kwargs,
        )


class CustomerDetailView(CustomerPermissionMixin, DetailView):
    model = Customer
    context_object_name = "customer"
    template_name = "customers/customer_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["purchase_history"] = Invoice.objects.filter(
            customer=self.object, status=Invoice.Status.PAID
        ).select_related("order__table").prefetch_related("payments")[:20]
        if has_customer_permission(self.request.user, "view_customeractivitylog"):
            context["log_page"] = Paginator(self.object.activity_logs.all(), 20).get_page(self.request.GET.get("page"))
        return context


class CustomerCreateView(CustomerPermissionMixin, FormView):
    customer_permission = "add_customer"
    form_class = CustomerForm
    template_name = "customers/customer_form.html"

    def form_valid(self, form):
        try:
            customer = create_customer(actor=self.request.user, **form.cleaned_data)
        except ValidationError as error:
            add_service_errors(form, error)
            return self.form_invalid(form)
        messages.success(self.request, f"Đã thêm khách hàng {customer.full_name}.")
        return HttpResponseRedirect(customer.get_absolute_url())


class CustomerUpdateView(CustomerPermissionMixin, FormView):
    customer_permission = "change_customer"
    form_class = CustomerForm
    template_name = "customers/customer_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        self.customer = get_object_or_404(Customer, pk=self.kwargs["pk"])
        kwargs["instance"] = self.customer
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["customer"] = self.customer
        return context

    def form_valid(self, form):
        try:
            customer = update_customer(actor=self.request.user, customer_id=self.customer.pk, **form.cleaned_data)
        except ValidationError as error:
            add_service_errors(form, error)
            return self.form_invalid(form)
        except Customer.DoesNotExist as error:
            raise Http404("Khách hàng không còn tồn tại.") from error
        messages.success(self.request, "Đã lưu thông tin khách hàng.")
        return HttpResponseRedirect(customer.get_absolute_url())


class CustomerDeleteView(CustomerPermissionMixin, FormView):
    customer_permission = "delete_customer"
    form_class = forms.Form
    template_name = "customers/customer_delete.html"
    success_url = reverse_lazy("customers:customer_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["customer"] = get_object_or_404(Customer, pk=self.kwargs["pk"])
        return context

    def form_valid(self, form):
        try:
            delete_customer(actor=self.request.user, customer_id=self.kwargs["pk"])
        except ValidationError as error:
            add_service_errors(form, error)
            return self.form_invalid(form)
        except Customer.DoesNotExist as error:
            raise Http404("Khách hàng không còn tồn tại.") from error
        messages.success(self.request, "Đã xóa khách hàng. Nhật ký thao tác được giữ lại.")
        return super().form_valid(form)


class CustomerLogListView(CustomerPermissionMixin, ListView):
    customer_permission = "view_customeractivitylog"
    template_name = "customers/customer_logs.html"
    paginate_by = 20

    def get_queryset(self):
        self.filter_form = CustomerLogFilterForm(self.request.GET)
        if not self.filter_form.is_valid():
            return CustomerActivityLog.objects.none()
        return customer_logs(query=self.filter_form.cleaned_data["q"], action=self.filter_form.cleaned_data["action"])

    def get_context_data(self, **kwargs):
        return super().get_context_data(
            filter_form=self.filter_form, query_string=filter_query_string(self.request.GET), **kwargs,
        )


class MembershipTierListView(CustomerPermissionMixin, ListView):
    customer_permission = "view_membershiptier"
    model = MembershipTier
    context_object_name = "tiers"
    template_name = "customers/membership_tier_list.html"


class MembershipTierCreateView(CustomerPermissionMixin, CreateView):
    customer_permission = "add_membershiptier"
    model = MembershipTier
    form_class = MembershipTierForm
    template_name = "customers/membership_tier_form.html"
    success_url = reverse_lazy("customers:membership_tier_list")

    def form_valid(self, form):
        with transaction.atomic():
            response = super().form_valid(form)
            recalculate_membership_tiers()
        messages.success(self.request, "Đã thêm hạng thành viên và cập nhật hạng khách hàng.")
        return response


class MembershipTierUpdateView(CustomerPermissionMixin, UpdateView):
    customer_permission = "change_membershiptier"
    model = MembershipTier
    form_class = MembershipTierForm
    template_name = "customers/membership_tier_form.html"
    success_url = reverse_lazy("customers:membership_tier_list")

    def form_valid(self, form):
        with transaction.atomic():
            response = super().form_valid(form)
            recalculate_membership_tiers()
        messages.success(self.request, "Đã cập nhật quy tắc và tính lại hạng khách hàng.")
        return response
