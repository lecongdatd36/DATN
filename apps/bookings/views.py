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
from apps.orders.permissions import has_order_permission
from .forms import (
    BookingFilterForm, BookingForm, SlotForm, TransitionForm, TransferTableForm,
    CancelSeatedVisitForm, BookingSettingsForm, PublicAvailabilityForm,
    PublicReservationForm, PublicReservationLookupForm,
)
from .models import Booking, BookingSettings, BookingSettingsLog
from .permissions import has_booking_permission
from .selectors import available_tables, booking_list, overdue_bookings, next_booking
from .services import (
    TRANSITIONS, create_public_booking, expire_overdue_bookings, save_booking,
    transfer_table, transition_booking, update_booking_settings,
)


@method_decorator(never_cache, name="dispatch")
class BookingPermissionMixin(AccessMixin):
    booking_permission = "view_booking"
    permission_denied_message = "Bạn không có quyền sử dụng chức năng đặt bàn."

    def dispatch(self, request, *args, **kwargs):
        if not has_booking_permission(request.user, self.booking_permission):
            return self.handle_no_permission()
        expire_overdue_bookings()
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
        from apps.orders.models import Invoice, Order
        context["visit_order"] = Order.objects.select_related("invoice").filter(booking=booking).first()
        visit_order = context["visit_order"]
        order_finished = visit_order is None or visit_order.status == Order.Status.CANCELLED
        if visit_order is not None and visit_order.status == Order.Status.COMPLETED:
            invoice = getattr(visit_order, "invoice", None)
            order_finished = invoice is not None and invoice.status == Invoice.Status.PAID
        context["order_blocks_completion"] = not order_finished
        now = timezone.now()
        context["overdue"] = booking.status == Booking.Status.SEATED and booking.ends_at <= now
        if context["overdue"]:
            context["next_visit"] = next_booking(booking)
        if booking.can_edit:
            context["overrunning_visit"] = overdue_bookings().filter(table_id=booking.table_id).exclude(pk=booking.pk).first()
        context["actions"] = []
        if has_booking_permission(self.request.user, "manage_booking"):
            for target in TRANSITIONS.get(booking.status, ()):
                if target == Booking.Status.COMPLETED and context["order_blocks_completion"]:
                    continue
                if target == Booking.Status.NO_SHOW and now < booking.starts_at:
                    continue
                if target == Booking.Status.SEATED and (now >= booking.ends_at or (now < booking.starts_at and timezone.localdate(now) != timezone.localdate(booking.starts_at))):
                    continue
                if target == Booking.Status.CONFIRMED and booking.ends_at <= now:
                    continue
                labels = {
                    Booking.Status.CONFIRMED: "Xác nhận đặt bàn", Booking.Status.SEATED: "Nhận khách",
                    Booking.Status.COMPLETED: "Hoàn tất", Booking.Status.CANCELLED: "Hủy lịch",
                    Booking.Status.NO_SHOW: "Đánh dấu không đến",
                }
                if target == Booking.Status.SEATED and has_order_permission(self.request.user, "manage_order"):
                    labels[target] = "Nhận khách & gọi món"
                context["actions"].append({"target": target, "label": labels[target]})
        context["early_arrival"] = booking.status == Booking.Status.CONFIRMED and now < booking.starts_at and timezone.localdate(now) == timezone.localdate(booking.starts_at)
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
        opens_order = self.target == Booking.Status.SEATED and has_order_permission(self.request.user, "manage_order")
        context.update(
            booking=self.booking,
            target_label="Nhận khách & gọi món" if opens_order else self.target.label,
            submit_label="Nhận khách & bắt đầu gọi món" if opens_order else "Xác nhận chuyển trạng thái",
            opens_order=opens_order,
            early_arrival=self.target == Booking.Status.SEATED and timezone.now() < self.booking.starts_at,
        )
        return context

    def form_valid(self, form):
        try:
            booking = transition_booking(actor=self.request.user, booking_id=self.booking.pk, target=self.target, **form.cleaned_data)
        except ValidationError as error:
            add_service_errors(form, error)
            return self.form_invalid(form)
        except Booking.DoesNotExist as error:
            raise Http404("Lịch đặt không còn tồn tại.") from error
        if self.target == Booking.Status.SEATED and has_order_permission(self.request.user, "manage_order"):
            from apps.orders import services as order_services
            try:
                order = order_services.open_order(actor=self.request.user, booking_id=booking.pk)
            except ValidationError as error:
                messages.warning(self.request, f"Đã nhận khách nhưng chưa mở được đơn: {'; '.join(error.messages)}")
                return HttpResponseRedirect(booking.get_absolute_url())
            messages.success(self.request, f"Đã nhận khách vào bàn {booking.table.code}. Hãy chọn món cho đơn {order.order_code}.")
            return HttpResponseRedirect(f'{reverse("sales:workspace")}?order={order.pk}#sales-menu')
        messages.success(self.request, f"{booking.booking_code}: {booking.get_status_display()}.")
        return HttpResponseRedirect(booking.get_absolute_url())


class TransferTableView(BookingPermissionMixin, FormView):
    booking_permission = "manage_booking"
    form_class = TransferTableForm
    template_name = "bookings/transfer_table.html"

    def dispatch(self, request, *args, **kwargs):
        self.booking = get_object_or_404(
            Booking.objects.select_related("table__area").prefetch_related("order__items"),
            pk=kwargs["pk"],
        )
        if self.booking.status != Booking.Status.SEATED:
            raise Http404("Lượt khách không còn ở trạng thái đang phục vụ.")
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["booking"] = self.booking
        kwargs["initial"] = {"expected_revision": self.booking.revision}
        return kwargs

    def get_context_data(self, **kwargs):
        return super().get_context_data(booking=self.booking, **kwargs)

    def form_valid(self, form):
        try:
            booking, old_table = transfer_table(
                actor=self.request.user,
                booking_id=self.booking.pk,
                table_id=form.cleaned_data["table"].pk,
                expected_revision=form.cleaned_data["expected_revision"],
            )
        except ValidationError as error:
            add_service_errors(form, error)
            return self.form_invalid(form)
        messages.success(self.request, f"Đã chuyển {booking.booking_code} từ bàn {old_table.code} sang bàn {booking.table.code}.")
        return HttpResponseRedirect(reverse("seating:table_list"))


class CancelSeatedVisitView(BookingPermissionMixin, FormView):
    booking_permission = "manage_booking"
    form_class = CancelSeatedVisitForm
    template_name = "bookings/cancel_seated.html"

    def dispatch(self, request, *args, **kwargs):
        self.booking = get_object_or_404(
            Booking.objects.select_related("table__area").prefetch_related("order__items"),
            pk=kwargs["pk"],
        )
        if self.booking.status != Booking.Status.SEATED:
            raise Http404("Bàn không còn ở trạng thái đang phục vụ.")
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        return {"expected_revision": self.booking.revision}

    def get_context_data(self, **kwargs):
        order = getattr(self.booking, "order", None)
        return super().get_context_data(booking=self.booking, visit_order=order, **kwargs)

    def form_valid(self, form):
        from apps.orders.services import cancel_table_visit
        try:
            booking, table_code = cancel_table_visit(
                actor=self.request.user,
                booking_id=self.booking.pk,
                **form.cleaned_data,
            )
        except ValidationError as error:
            add_service_errors(form, error)
            return self.form_invalid(form)
        messages.success(self.request, f"Đã hủy lượt khách {booking.booking_code} và giải phóng bàn {table_code}.")
        return HttpResponseRedirect(reverse("seating:table_list"))


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


class PublicTableCheckView(FormView):
    form_class = PublicAvailabilityForm
    template_name = "customer/table_check.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self.request.GET:
            kwargs["data"] = self.request.GET
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = context["form"]
        if form.is_bound and form.is_valid():
            result = available_tables(
                starts_at=form.cleaned_data["starts_at"],
                ends_at=form.cleaned_data["ends_at"],
                party_size=form.cleaned_data["party_size"],
            )
            if form.cleaned_data.get("area"):
                result = result.filter(area=form.cleaned_data["area"])
            context["available_areas"] = result.values("area__name").distinct().order_by("area__name")
            context["searched"] = True
        return context


class PublicReservationCreateView(FormView):
    form_class = PublicReservationForm
    template_name = "customer/reservation_form.html"

    def form_valid(self, form):
        try:
            booking = create_public_booking(
                full_name=form.cleaned_data["full_name"],
                phone=form.cleaned_data["phone"],
                starts_at=form.cleaned_data["starts_at"],
                party_size=form.cleaned_data["party_size"],
                area_id=form.cleaned_data["area"].pk if form.cleaned_data.get("area") else None,
                duration_minutes=form.cleaned_data.get("duration_minutes"),
                note=form.cleaned_data.get("note", ""),
            )
        except ValidationError as error:
            add_service_errors(form, error)
            return self.form_invalid(form)
        self.request.session["public_booking_success"] = {
            "booking_id": booking.pk,
            "booking_code": booking.booking_code,
            "starts_at": booking.starts_at.isoformat(),
            "ends_at": booking.ends_at.isoformat(),
            "party_size": booking.party_size,
            "area_name": booking.table.area.name,
            "status": booking.get_status_display(),
        }
        return HttpResponseRedirect(reverse("customer_reservations:success"))


class PublicReservationSuccessView(FormView):
    template_name = "customer/reservation_success.html"
    form_class = PublicReservationLookupForm

    def get(self, request, *args, **kwargs):
        success = request.session.pop("public_booking_success", None)
        if not success:
            return HttpResponseRedirect(reverse("customer_reservations:lookup"))
        return self.render_to_response(self.get_context_data(success=success))


class PublicReservationLookupView(FormView):
    form_class = PublicReservationLookupForm
    template_name = "customer/reservation_lookup.html"

    def form_valid(self, form):
        code = form.cleaned_data["reservation_code"]
        try:
            booking_id = int(code[2:])
        except ValueError:
            form.add_error("reservation_code", "Mã đặt bàn không hợp lệ.")
            return self.form_invalid(form)
        booking = Booking.objects.filter(pk=booking_id, is_walk_in=False, customer_phone=form.cleaned_data["phone"]).first()
        if booking is None:
            form.add_error(None, "Không tìm thấy đặt bàn với mã và số điện thoại này.")
            return self.form_invalid(form)
        verified = set(self.request.session.get("public_booking_verified", []))
        verified.add(str(booking.pk))
        self.request.session["public_booking_verified"] = list(verified)
        return HttpResponseRedirect(reverse("customer_reservations:status", args=[booking.pk]))


class PublicReservationStatusView(DetailView):
    template_name = "customer/reservation_status.html"
    context_object_name = "booking"
    queryset = Booking.objects.select_related("table__area")

    def get_object(self, queryset=None):
        expire_overdue_bookings()
        return super().get_object(queryset)

    def dispatch(self, request, *args, **kwargs):
        if str(kwargs["pk"]) not in request.session.get("public_booking_verified", []):
            return HttpResponseRedirect(reverse("customer_reservations:lookup"))
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        status_order = [Booking.Status.PENDING, Booking.Status.CONFIRMED, Booking.Status.SEATED, Booking.Status.COMPLETED]
        current_index = status_order.index(self.object.status) if self.object.status in status_order else -1
        context["timeline"] = [
            {"label": status.label, "done": current_index >= status_index}
            for status_index, status in enumerate(status_order)
        ]
        context["cancelled"] = self.object.status in (Booking.Status.CANCELLED, Booking.Status.NO_SHOW)
        return context
