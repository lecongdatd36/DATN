from urllib.parse import urlencode
from django.contrib import messages
from django.contrib.auth.mixins import AccessMixin
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.generic import DetailView, FormView, ListView

from core.forms import add_service_errors, filter_query_string
from .forms import BookingFilterForm, BookingForm, SlotForm, TransitionForm, BookingSettingsForm
from .models import Booking, BookingSettings, BookingSettingsLog
from .permissions import has_booking_permission
from .selectors import available_tables, booking_list, overdue_bookings, next_booking
from .services import TRANSITIONS, save_booking, transition_booking, update_booking_settings


@method_decorator(never_cache, name="dispatch")
class BookingPermissionMixin(AccessMixin):
    booking_permission = "view_booking"
    permission_denied_message = "Bạn không có quyền sử dụng chức năng đặt bàn."

    def dispatch(self, request, *args, **kwargs):
        if not has_booking_permission(request.user, self.booking_permission):
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)


class BookingListView(BookingPermissionMixin, ListView):
    template_name = "bookings/list.html"
    paginate_by = 20

    def get_queryset(self):
        self.filter_form = BookingFilterForm(self.request.GET)
        return booking_list(**self.filter_form.cleaned_data) if self.filter_form.is_valid() else Booking.objects.none()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(filter_form=self.filter_form, query_string=filter_query_string(self.request.GET), **kwargs)
        context["overrun_alerts"] = list(overdue_bookings()[:10])
        for booking in context["overrun_alerts"]:
            booking.next_visit = next_booking(booking)
        return context


class BookingDetailView(BookingPermissionMixin, DetailView):
    queryset = Booking.objects.select_related("table", "table__area", "customer")
    context_object_name = "booking"
    template_name = "bookings/detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        booking = self.object
        now = timezone.now()
        context["overdue"] = booking.status == Booking.Status.SEATED and booking.ends_at <= now
        if context["overdue"]:
            context["next_visit"] = next_booking(booking)
        if booking.can_edit:
            context["overrunning_visit"] = overdue_bookings().filter(table_id=booking.table_id).exclude(pk=booking.pk).first()
        context["actions"] = []
        if has_booking_permission(self.request.user, "manage_booking"):
            for target in TRANSITIONS.get(booking.status, ()):
                if target == Booking.Status.NO_SHOW and now < booking.starts_at:
                    continue
                if target == Booking.Status.SEATED and not booking.starts_at <= now < booking.ends_at:
                    continue
                if target == Booking.Status.CONFIRMED and booking.ends_at <= now:
                    continue
                labels = {
                    Booking.Status.CONFIRMED: "Xác nhận đặt bàn", Booking.Status.SEATED: "Nhận khách",
                    Booking.Status.COMPLETED: "Hoàn tất", Booking.Status.CANCELLED: "Hủy lịch",
                    Booking.Status.NO_SHOW: "Đánh dấu không đến",
                }
                context["actions"].append({"target": target, "label": labels[target]})
        if has_booking_permission(self.request.user, "view_bookingactivitylog"):
            context["log_page"] = Paginator(booking.activity_logs.all(), 20).get_page(self.request.GET.get("page"))
        return context


class BookingFormView(BookingPermissionMixin, FormView):
    booking_permission = "manage_booking"
    form_class = BookingForm
    template_name = "bookings/form.html"

    def get_form_kwargs(self):
        self.booking = get_object_or_404(Booking.objects.select_related("customer"), pk=self.kwargs["pk"]) if "pk" in self.kwargs else None
        kwargs = super().get_form_kwargs()
        kwargs["booking"] = self.booking
        if self.booking:
            kwargs["initial"] = {
                "customer_phone": self.booking.customer.phone, "table": self.booking.table_id,
                "party_size": self.booking.party_size, "starts_at": self.booking.starts_at, "duration_minutes": self.booking.duration_minutes,
                "expected_revision": self.booking.revision,
            }
        else:
            kwargs["initial"] = {key: self.request.GET[key] for key in ("customer_phone", "table", "party_size", "starts_at", "duration_minutes") if key in self.request.GET}
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["booking"] = self.booking
        return context

    def form_valid(self, form):
        data = form.cleaned_data.copy()
        data.pop("ends_at")
        data["table_id"] = data.pop("table").pk
        try:
            booking = save_booking(actor=self.request.user, booking_id=self.booking.pk if self.booking else None, **data)
        except ValidationError as error:
            add_service_errors(form, error)
            return self.form_invalid(form)
        except Booking.DoesNotExist as error:
            raise Http404("Lịch đặt không còn tồn tại.") from error
        messages.success(self.request, "Đã lưu lịch đặt bàn.")
        return HttpResponseRedirect(booking.get_absolute_url())


class BookingTransitionView(BookingPermissionMixin, FormView):
    booking_permission = "manage_booking"
    form_class = TransitionForm
    template_name = "bookings/transition.html"

    def get_form_kwargs(self):
        self.booking = get_object_or_404(Booking.objects.select_related("table"), pk=self.kwargs["pk"])
        try:
            self.target = Booking.Status(self.kwargs["target"])
        except ValueError as error:
            raise Http404("Trạng thái không hợp lệ.") from error
        kwargs = super().get_form_kwargs()
        kwargs["initial"] = {"expected_status": self.booking.status, "expected_revision": self.booking.revision}
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(booking=self.booking, target_label=self.target.label)
        return context

    def form_valid(self, form):
        try:
            booking = transition_booking(actor=self.request.user, booking_id=self.booking.pk, target=self.target, **form.cleaned_data)
        except ValidationError as error:
            add_service_errors(form, error)
            return self.form_invalid(form)
        except Booking.DoesNotExist as error:
            raise Http404("Lịch đặt không còn tồn tại.") from error
        messages.success(self.request, f"{booking.booking_code}: {booking.get_status_display()}.")
        return HttpResponseRedirect(booking.get_absolute_url())


class AvailabilityView(BookingPermissionMixin, FormView):
    form_class = SlotForm
    template_name = "bookings/availability.html"
    http_method_names = ["get", "head", "options"]

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self.request.GET:
            kwargs["data"] = self.request.GET
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = context["form"]
        if form.is_bound and form.is_valid():
            if form.cleaned_data["starts_at"] < timezone.now():
                form.add_error("starts_at", "Chọn giờ đến ở tương lai.")
                return context
            context["searched"] = True
            result = available_tables(**{key: form.cleaned_data[key] for key in ("starts_at", "ends_at", "party_size")})
            context["planned_start"] = form.cleaned_data["starts_at"]
            context["planned_end"] = form.cleaned_data["ends_at"]
            context["page_obj"] = Paginator(result, 20).get_page(self.request.GET.get("page"))
            context["query_string"] = filter_query_string(self.request.GET)
            values = {key: timezone.localtime(value).strftime("%Y-%m-%dT%H:%M") if key == "starts_at" else value for key, value in form.cleaned_data.items() if key != "ends_at"}
            for table in context["page_obj"]:
                table.booking_url = reverse("bookings:create") + "?" + urlencode({**values, "table": table.pk})
        return context


class BookingSettingsView(BookingPermissionMixin, FormView):
    booking_permission = "configure_bookings"
    form_class = BookingSettingsForm
    template_name = "bookings/settings.html"

    def get_initial(self):
        settings = BookingSettings.objects.get(pk=1)
        return {"default_duration_minutes": settings.default_duration_minutes, "expected_revision": settings.revision}

    def get_context_data(self, **kwargs):
        return super().get_context_data(settings_logs=BookingSettingsLog.objects.all()[:20], **kwargs)

    def form_valid(self, form):
        try:
            update_booking_settings(actor=self.request.user, **form.cleaned_data)
        except ValidationError as error:
            add_service_errors(form, error)
            return self.form_invalid(form)
        messages.success(self.request, "Đã lưu thời lượng mặc định. Các lịch đã đặt giữ nguyên giờ dự kiến.")
        return HttpResponseRedirect(reverse("bookings:settings"))
