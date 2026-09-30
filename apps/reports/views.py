import csv
from datetime import datetime, time, timedelta

from django.contrib.auth.mixins import AccessMixin
from django.http import HttpResponse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from .forms import ReportFilterForm
from .permissions import has_report_permission
from .selectors import paid_invoices_for_export, report_data


class ReportPermissionMixin(AccessMixin):
    def dispatch(self, request, *args, **kwargs):
        if not has_report_permission(request.user):
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)


def _period_bounds(date_from, date_to):
    current_tz = timezone.get_current_timezone()
    start_at = timezone.make_aware(datetime.combine(date_from, time.min), current_tz)
    end_at = timezone.make_aware(datetime.combine(date_to + timedelta(days=1), time.min), current_tz)
    return start_at, end_at


def _filter_form(request):
    if request.GET:
        return ReportFilterForm(request.GET)
    date_from, date_to = ReportFilterForm.default_period()
    return ReportFilterForm(initial={"date_from": date_from, "date_to": date_to})


class ReportDashboardView(ReportPermissionMixin, TemplateView):
    template_name = "reports/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = _filter_form(self.request)
        context["filter_form"] = form
        if self.request.GET:
            if not form.is_valid():
                return context
            date_from = form.cleaned_data["date_from"]
            date_to = form.cleaned_data["date_to"]
        else:
            date_from, date_to = ReportFilterForm.default_period()
        start_at, end_at = _period_bounds(date_from, date_to)
        context.update(report_data(start_at, end_at))
        context.update({"report_ready": True, "date_from": date_from, "date_to": date_to})
        return context


class RevenueExportView(ReportPermissionMixin, View):
    def get(self, request):
        form = ReportFilterForm(request.GET)
        if not form.is_valid():
            response = HttpResponse("Khoảng ngày không hợp lệ.", content_type="text/plain; charset=utf-8", status=400)
            return response
        date_from = form.cleaned_data["date_from"]
        date_to = form.cleaned_data["date_to"]
        start_at, end_at = _period_bounds(date_from, date_to)

        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="doanh-thu-{date_from:%Y%m%d}-{date_to:%Y%m%d}.csv"'
        response.write("\ufeff")
        writer = csv.writer(response)
        writer.writerow(["Mã hóa đơn", "Mã thanh toán chung", "Mã đơn", "Bàn", "Khu vực", "Khách hàng", "Thời gian chốt", "Tổng tiền", "Phương thức thanh toán"])
        for invoice in paid_invoices_for_export(start_at, end_at):
            booking = invoice.order.booking
            table = invoice.order.table or (booking.table if booking else None)
            methods = ", ".join(dict.fromkeys(payment.get_method_display() for payment in invoice.payments.all()))
            batch_codes = ", ".join(dict.fromkeys(payment.batch.batch_code for payment in invoice.payments.all() if payment.batch_id))
            writer.writerow([
                invoice.invoice_code,
                batch_codes,
                invoice.order.order_code,
                table.code if table else "",
                table.area.name if table else "",
                invoice.customer.full_name if invoice.customer_id else (booking.customer_name if booking else "Khách vãng lai"),
                timezone.localtime(invoice.closed_at).strftime("%d/%m/%Y %H:%M"),
                invoice.total,
                methods or invoice.payment_method,
            ])
        return response
