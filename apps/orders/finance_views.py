from uuid import uuid4
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Sum, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from core.permissions import can_manage_accounts
from . import finance_services as services
from .models import CashShift, FinanceLog, InvoiceRefund, Payment, ZaloPayTransaction
from .permissions import has_order_permission


class OpenForm(forms.Form):
    opening_amount = forms.DecimalField(label="Tiền mặt đầu ca", min_value=0, max_digits=12, decimal_places=0)
    note = forms.CharField(label="Ghi chú đầu ca", max_length=500, required=False)


class CloseForm(forms.Form):
    revision = forms.IntegerField(min_value=1, widget=forms.HiddenInput)
    counted_amount = forms.DecimalField(label="Tiền mặt thực đếm", min_value=0, max_digits=12, decimal_places=0)
    note = forms.CharField(label="Bàn giao / lý do chênh lệch", max_length=1000, required=False, widget=forms.Textarea(attrs={"rows": 2}))


class RefundForm(forms.Form):
    payment_id = forms.IntegerField(label="Phiếu thu", min_value=1)
    amount = forms.DecimalField(label="Số tiền hoàn", min_value=1, max_digits=12, decimal_places=0)
    method = forms.ChoiceField(label="Cách hoàn", choices=InvoiceRefund._meta.get_field("method").choices)
    reason = forms.CharField(label="Lý do hoàn", min_length=5, max_length=1000, widget=forms.Textarea(attrs={"rows": 2}))
    request_key = forms.UUIDField(widget=forms.HiddenInput)


class RefundActionForm(forms.Form):
    revision = forms.IntegerField(min_value=1)
    action = forms.ChoiceField(choices=(("approve", "Duyệt"), ("reject", "Từ chối"), ("complete", "Ghi nhận đã hoàn")))
    note = forms.CharField(min_length=5, max_length=1000)
    reference = forms.CharField(max_length=100, required=False)
    verified = forms.BooleanField(required=False)


class ReconcileForm(forms.Form):
    transaction_id = forms.IntegerField(min_value=1)
    outcome = forms.ChoiceField(choices=(("REFUNDED", "Đã hoàn khoản nhận thừa"), ("APPLIED", "Áp dụng vào đơn đang chờ thu"), ("MATCHED", "Khớp phiếu thu ZaloPay có sẵn")))
    reference = forms.CharField(min_length=3, max_length=100)
    reason = forms.CharField(min_length=5, max_length=1000)
    verified = forms.BooleanField()


def permit(request):
    if not has_order_permission(request.user, "collect_payment"):
        raise PermissionDenied


def valid(form):
    if not form.is_valid():
        raise ValidationError([f"{form.fields[key].label or key}: {' '.join(errors)}" for key, errors in form.errors.items()])
    return form.cleaned_data


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def shifts(request):
    permit(request)
    form = OpenForm(request.POST or None)
    if request.method == "POST":
        try:
            row = services.open_shift(actor=request.user, **valid(form))
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, "Đã mở ca thu ngân.")
            return redirect("orders:cash_shift_detail", pk=row.pk)
    rows = CashShift.objects.select_related("cashier", "reviewed_by")
    manager = can_manage_accounts(request.user)
    if not manager:
        rows = rows.filter(cashier=request.user)
    active = CashShift.objects.filter(cashier=request.user, status="OPEN").first()
    unassigned = Payment.objects.filter(performed_by=request.user, cash_shift__isnull=True).exclude(method="DEPOSIT").count()
    return render(request, "orders/finance/shifts.html", {"shifts": rows[:50], "form": form, "active_shift": active,
        "unassigned_receipts": unassigned, "finance_manager": manager})


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def shift_detail(request, pk):
    permit(request)
    row = get_object_or_404(CashShift.objects.select_related("cashier", "reviewed_by"), pk=pk)
    manager = can_manage_accounts(request.user)
    if row.cashier_id != request.user.pk and not manager:
        raise PermissionDenied
    form = CloseForm(request.POST or None, initial={"revision": row.revision})
    if request.method == "POST":
        try:
            if request.POST.get("action") == "review":
                revision = forms.IntegerField(min_value=1).clean(request.POST.get("revision"))
                services.review_shift(actor=request.user, shift_id=row.pk, revision=revision, note=request.POST.get("note"))
            else:
                services.close_shift(actor=request.user, shift_id=row.pk, **valid(form))
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
        else:
            messages.success(request, "Đã cập nhật ca thu ngân.")
            return redirect("orders:cash_shift_detail", pk=row.pk)
    totals = row.totals_snapshot if row.status != "OPEN" else services.shift_totals(row)
    labels = dict(Payment.Method.choices)
    methods = sorted(set(totals.get("receipts", {})) | set(totals.get("refunds", {})))
    return render(request, "orders/finance/shift_detail.html", {"shift": row, "form": form, "totals": totals,
        "method_totals": [{"label": labels.get(key, key), "received": totals.get("receipts", {}).get(key, "0"), "refunded": totals.get("refunds", {}).get(key, "0")} for key in methods],
        "finance_manager": manager, "logs": row.logs.select_related("actor")[:30]})


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def refunds(request):
    permit(request)
    form = RefundForm(request.POST or None, initial={"request_key": uuid4()})
    if request.method == "POST":
        try:
            services.request_refund(actor=request.user, **valid(form))
        except (Payment.DoesNotExist, ValidationError) as error:
            form.add_error(None, " ".join(error.messages) if isinstance(error, ValidationError) else "Phiếu thu không tồn tại.")
        else:
            messages.success(request, "Đã lập yêu cầu hoàn tiền, chờ quản lý duyệt.")
            return redirect("orders:refunds")
    payments = Payment.objects.select_related("invoice").exclude(invoice__status="CANCELLED").annotate(
        reserved=Sum("refunds__amount", filter=Q(refunds__status__in=("REQUESTED", "APPROVED", "COMPLETED"))))
    query = request.GET.get("q", "").strip()[:100]
    if query:
        payments = payments.filter(Q(invoice__invoice_code__icontains=query) | Q(invoice__order__order_code__icontains=query))
    options = []
    for payment in payments.order_by("-created_at", "-pk")[:100]:
        remaining = payment.amount - (payment.reserved or 0)
        if remaining > 0:
            options.append((payment.pk, f"{payment.invoice.invoice_code} · {payment.get_method_display()} · còn được yêu cầu hoàn {remaining:,.0f} đ"))
    form.fields["payment_id"].widget = forms.Select(choices=options)
    rows = InvoiceRefund.objects.select_related("invoice", "payment", "requested_by", "reviewed_by", "completed_by")
    if query:
        rows = rows.filter(invoice__invoice_code__icontains=query)
    return render(request, "orders/finance/refunds.html", {"form": form, "refunds": rows[:50], "query": query,
        "finance_manager": can_manage_accounts(request.user)})


@login_required
@never_cache
@require_http_methods(["POST"])
def refund_action(request, pk):
    permit(request)
    get_object_or_404(InvoiceRefund, pk=pk)
    try:
        data = valid(RefundActionForm(request.POST))
        action = data.pop("action")
        if action == "complete":
            services.complete_refund(actor=request.user, refund_id=pk, **data)
        else:
            services.review_refund(actor=request.user, refund_id=pk, revision=data["revision"],
                approve=action == "approve", note=data["note"])
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(request, "Đã cập nhật phiếu hoàn tiền.")
    return redirect("orders:refunds")


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def reconciliation(request):
    permit(request)
    if not can_manage_accounts(request.user):
        raise PermissionDenied
    if request.method == "POST":
        try:
            services.reconcile_zalopay(actor=request.user, **valid(ReconcileForm(request.POST)))
        except (ValidationError, ZaloPayTransaction.DoesNotExist) as error:
            messages.error(request, " ".join(error.messages) if isinstance(error, ValidationError) else "Giao dịch không tồn tại.")
        else:
            messages.success(request, "Đã ghi nhận kết quả đối soát.")
        return redirect("orders:reconciliation")
    rows = ZaloPayTransaction.objects.filter(order_payment__isnull=False).filter(Q(status="REVIEW") | Q(reconciliation__isnull=False)).select_related("order_payment__order", "reconciliation__resolved_by")
    return render(request, "orders/finance/reconciliation.html", {"transactions": rows.order_by("-paid_at", "-pk")[:100],
        "finance_manager": True})
