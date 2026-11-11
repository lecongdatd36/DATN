import csv
from datetime import timedelta
from functools import wraps
import json

from django.contrib import messages
from django.conf import settings
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST
from django.views.decorators.debug import sensitive_post_parameters

from core.forms import add_service_errors, filter_query_string
from core.permissions import can_manage_accounts
from apps.employees.models import EmployeeProfile
from . import services
from .face import readiness
from .face import pose_feedback
from .forms import CorrectionForm, DeviceForm, RangeForm, ScheduleForm, ShiftForm
from .models import Attendance, AttendanceLog, FaceProfile, KioskDevice, WorkSchedule, WorkShift


def management(view):
    @login_required
    @never_cache
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not can_manage_accounts(request.user):
            raise PermissionDenied("Bạn không có quyền quản lý ca làm và công.")
        return view(request, *args, **kwargs)
    return wrapped


def filtered_schedules(request, *, personal=False, monthly=False):
    today = timezone.localdate()
    start = today.replace(day=1) if monthly else today-timedelta(days=today.weekday())
    end = (start.replace(day=28)+timedelta(days=4)).replace(day=1)-timedelta(days=1) if monthly else start+timedelta(days=6)
    form = RangeForm(request.GET or {"start": start, "end": end})
    rows = WorkSchedule.objects.select_related("employee__user", "shift", "attendance").all()
    if personal:
        rows = rows.filter(employee__user=request.user).exclude(status=WorkSchedule.Status.DRAFT)
    if not form.is_valid():
        return form, rows.none()
    data = form.cleaned_data
    rows = rows.filter(work_date__range=(data["start"], data["end"]))
    if data["employee"]:
        rows = rows.filter(employee=data["employee"])
    return form, rows


@management
def schedules(request):
    form = ScheduleForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                for employee in form.cleaned_data["employees"]:
                    services.assign_schedule(actor=request.user, employee_id=employee.pk, shift_id=form.cleaned_data["shift"].pk,
                        work_date=form.cleaned_data["work_date"], note=form.cleaned_data["note"])
        except ValidationError as error:
            add_service_errors(form, error)
        else:
            messages.success(request, "Đã tạo lịch nháp. Kiểm tra và công bố để nhân viên chấm công.")
            day = form.cleaned_data["work_date"]
            week = day-timedelta(days=day.weekday())
            return redirect(f"{reverse('workforce:schedules')}?start={week}&end={week+timedelta(days=6)}")
    filters, rows = filtered_schedules(request)
    return render(request, "workforce/schedules.html", {"form": form, "filters": filters, "page_obj": Paginator(rows, 50).get_page(request.GET.get("page")), "query_string": filter_query_string(request.GET)})


@management
@require_POST
def schedule_action(request, pk):
    schedule = get_object_or_404(WorkSchedule, pk=pk)
    try:
        services.change_schedule(actor=request.user, schedule_id=pk, revision=int(request.POST.get("revision", "0")), action=request.POST.get("action"))
    except (ValidationError, ValueError) as error:
        messages.error(request, " ".join(error.messages) if isinstance(error, ValidationError) else "Phiên bản lịch không hợp lệ.")
    else:
        messages.success(request, "Đã cập nhật lịch làm việc.")
    week = schedule.work_date-timedelta(days=schedule.work_date.weekday())
    return redirect(f"{reverse('workforce:schedules')}?start={week}&end={week+timedelta(days=6)}")


@management
def shifts(request, pk=None):
    shift = get_object_or_404(WorkShift, pk=pk) if pk else None
    form = ShiftForm(request.POST or None, instance=shift)
    if request.method == "POST" and form.is_valid():
        try:
            services.save_shift(actor=request.user, data=form.cleaned_data, shift_id=pk)
        except ValidationError as error:
            add_service_errors(form, error)
        else:
            messages.success(request, "Đã lưu ca. Các lịch đã phân giữ nguyên giờ và quy định cũ.")
            return redirect("workforce:shifts")
    return render(request, "workforce/shifts.html", {"form": form, "shifts": WorkShift.objects.all(), "editing": shift})


@login_required
@never_cache
def mine(request):
    filters, rows = filtered_schedules(request, personal=True)
    # Do not enumerate other employees in a personal filter widget.
    filters.fields.pop("employee")
    return render(request, "workforce/mine.html", {"filters": filters, "rows": rows})


@management
def timesheet(request):
    filters, rows = filtered_schedules(request, monthly=True)
    rows = rows.exclude(status=WorkSchedule.Status.CANCELLED)
    summary = {}
    for schedule in rows:
        item = summary.setdefault(schedule.employee_id, {"employee": schedule.employee, "shifts": 0, "approved": 0, "minutes": 0, "late": 0, "early": 0, "absent": 0})
        item["shifts"] += 1
        attendance = getattr(schedule, "attendance", None)
        if attendance and attendance.review == Attendance.Review.APPROVED:
            item["approved"] += 1
            item["minutes"] += attendance.worked_minutes
            item["late"] += int(attendance.is_late)
            item["early"] += int(attendance.early_minutes > 0)
            item["absent"] += int(attendance.checked_in_at is None)
    for item in summary.values():
        item["hours"] = round(item["minutes"] / 60, 2)
    if request.GET.get("export") == "csv" and filters.is_valid():
        response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
        response["Content-Disposition"] = 'attachment; filename="bang-cong.csv"'
        response.write("\ufeff")
        writer = csv.writer(response)
        writer.writerow(("Mã nhân viên", "Họ tên", "Ca được phân", "Công đã duyệt", "Phút công đã duyệt", "Lượt trễ", "Lượt về sớm", "Vắng"))
        for item in summary.values():
            # Prefix untrusted spreadsheet strings to prevent CSV formula execution.
            safe = lambda value: "'"+value if value.lstrip().startswith(("=", "+", "-", "@")) else value
            writer.writerow((safe(item["employee"].employee_code), safe(item["employee"].full_name), item["shifts"], item["approved"], item["minutes"], item["late"], item["early"], item["absent"]))
        return response
    return render(request, "workforce/timesheet.html", {"filters": filters, "summary": summary.values(), "page_obj": Paginator(rows, 50).get_page(request.GET.get("page")), "query_string": filter_query_string(request.GET)})


@management
def attendance_detail(request, pk):
    schedule = get_object_or_404(WorkSchedule.objects.select_related("employee", "attendance"), pk=pk)
    attendance = getattr(schedule, "attendance", None)
    form = CorrectionForm(request.POST or None, initial={"revision": attendance.revision if attendance else 0,
        "checked_in": attendance.checked_in_at if attendance else None, "checked_out": attendance.checked_out_at if attendance else None})
    if request.method == "POST" and form.is_valid():
        try:
            services.review_attendance(actor=request.user, schedule_id=pk, action=request.POST.get("action"), **form.cleaned_data)
        except ValidationError as error:
            add_service_errors(form, error)
        else:
            messages.success(request, "Đã cập nhật bảng công.")
            return redirect("workforce:attendance", pk=pk)
    return render(request, "workforce/attendance.html", {"schedule": schedule, "attendance": attendance, "form": form,
        "logs": AttendanceLog.objects.filter(schedule=schedule).select_related("actor", "device")[:50]})


@management
@ensure_csrf_cookie
def faces(request, pk=None):
    employee = get_object_or_404(EmployeeProfile, pk=pk) if pk else None
    error, ready = readiness()
    return render(request, "workforce/faces.html", {"employee": employee,
        "employees": EmployeeProfile.objects.select_related("face_profile", "job_position").order_by("employee_code"),
        "ready": ready, "readiness_error": error})


@management
@ensure_csrf_cookie
def face_test(request):
    error, ready = readiness()
    return render(request, "workforce/face_test.html", {
        "ready": ready, "readiness_error": error,
        "recognition_config": {"threshold": settings.ATTENDANCE_FACE_THRESHOLD,
            "margin": settings.ATTENDANCE_FACE_MARGIN},
    })


@management
@require_POST
@sensitive_post_parameters()
def face_test_api(request):
    """Manager-only, transient recognition preview; never starts a clock challenge."""
    from apps.employees.models import EmploymentStatus
    from .face import MODEL_VERSION, best_match, extract_frame

    error, ready = readiness()
    if not ready:
        return JsonResponse({"ok": False, "identified": False, "recorded": False,
            "code": "not_ready", "message": error}, status=503)
    try:
        data = payload(request, maximum=700_000)
        sample = extract_frame(data.get("frame"))
    except ValidationError as error:
        return JsonResponse({"ok": False, "identified": False, "recorded": False,
            "code": "invalid_frame", "message": " ".join(error.messages)}, status=400)
    profiles = FaceProfile.objects.select_related("employee").filter(model_version=MODEL_VERSION,
        employee__employment_status=EmploymentStatus.WORKING,
        employee__user__is_active=True, employee__job_position__is_active=True)
    if not profiles.exists():
        return JsonResponse({"ok": True, "identified": False, "recorded": False,
            "code": "no_profiles", "message": "Chưa có mẫu khuôn mặt hợp lệ của nhân viên đang làm việc. Hãy đăng ký mẫu trước."})
    match = best_match(sample["vector"], profiles)
    if not match:
        return JsonResponse({"ok": True, "identified": False, "recorded": False,
            "code": "no_match", "message": "Chưa tìm thấy mẫu khớp đủ ngưỡng hoặc kết quả chưa phân biệt được giữa các nhân viên. Hãy nhìn thẳng, điều chỉnh ánh sáng và thử lại."})
    profile, score = match
    return JsonResponse({"ok": True, "identified": True, "recorded": False,
        "code": "identified", "name": profile.employee.full_name,
        "employee_code": profile.employee.employee_code, "similarity": round(score, 4),
        "threshold": settings.ATTENDANCE_FACE_THRESHOLD,
        "message": "Đã tìm thấy mẫu khuôn mặt phù hợp. Đây là kết quả kiểm thử, chưa ghi nhận công; mở trang chấm công và bấm Chấm công để xác minh động tác. Hệ thống tự xác định vào ca hoặc ra ca."})


def payload(request, maximum=2_000_000):
    if request.content_type != "application/json" or len(request.body) > maximum:
        raise ValidationError("Yêu cầu không hợp lệ hoặc quá lớn.")
    try:
        data = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        raise ValidationError("Dữ liệu JSON không hợp lệ.") from None
    if not isinstance(data, dict):
        raise ValidationError("Dữ liệu không hợp lệ.")
    return data


@management
@require_POST
@sensitive_post_parameters()
def face_save(request, pk):
    get_object_or_404(EmployeeProfile, pk=pk)
    try:
        data = payload(request)
        services.enroll_face(actor=request.user, employee_id=pk, frames=data.get("frames"), consent=data.get("consent"))
    except ValidationError as error:
        return JsonResponse({"ok": False, "message": " ".join(error.messages)}, status=400)
    return JsonResponse({"ok": True, "message": "Đã lưu 3 mẫu khuôn mặt. Ảnh camera không được lưu."})


@management
@require_POST
def face_delete(request, pk):
    get_object_or_404(EmployeeProfile, pk=pk)
    services.delete_face(actor=request.user, employee_id=pk)
    messages.success(request, "Đã xóa mẫu khuôn mặt và hủy lượt xác minh đang dùng hồ sơ này.")
    return redirect("workforce:faces")


@management
def devices(request):
    form = DeviceForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        _, raw = services.activate_device(actor=request.user, name=form.cleaned_data["name"], previous_token=request.COOKIES.get(services.COOKIE_NAME, ""))
        logout(request)
        response = redirect("workforce:kiosk")
        response.set_cookie(services.COOKIE_NAME, raw, max_age=30*86400, httponly=True, secure=request.is_secure(), samesite="Strict", path="/cham-cong/kiosk/")
        return response
    return render(request, "workforce/devices.html", {"form": form, "devices": KioskDevice.objects.order_by("-created_at")})


@management
@require_POST
def device_revoke(request, pk):
    get_object_or_404(KioskDevice, pk=pk)
    services.revoke_device(actor=request.user, device_id=pk)
    messages.success(request, "Đã thu hồi quyền chấm công của thiết bị.")
    return redirect("workforce:devices")


@never_cache
@ensure_csrf_cookie
def point(request):
    # Anonymous shared page: the browser session binds each face challenge only.
    # It grants no HR, employee-account, or administration permissions.
    request.session["attendance_point"] = True
    return render(request, "workforce/kiosk.html", {"shared_point": True,
        "recognition_config": {"threshold": settings.ATTENDANCE_FACE_THRESHOLD}})


@never_cache
@require_POST
@sensitive_post_parameters()
def point_api(request):
    if request.session.get("attendance_point") is not True:
        return JsonResponse({"ok": False, "done": True, "recorded": False,
            "message": "Phiên chấm công đã hết hạn. Hãy tải lại trang."}, status=403)
    return camera_response(request, {"session_key": request.session.session_key})


@never_cache
@ensure_csrf_cookie
def kiosk(request):
    try:
        device = services.get_device(request.COOKIES.get(services.COOKIE_NAME))
    except PermissionDenied:
        return render(request, "workforce/kiosk.html", {"device": None}, status=403)
    return render(request, "workforce/kiosk.html", {"device": device,
        "recognition_config": {"threshold": settings.ATTENDANCE_FACE_THRESHOLD}})


@never_cache
@require_POST
@sensitive_post_parameters()
def kiosk_api(request):
    try:
        services.get_device(request.COOKIES.get(services.COOKIE_NAME))
    except PermissionDenied:
        return JsonResponse({"ok": False, "done": True, "message": "Máy chưa được kích hoạt, đã hết hạn hoặc bị thu hồi."}, status=403)
    return camera_response(request, {"raw_token": request.COOKIES.get(services.COOKIE_NAME)})


def camera_response(request, source):
    try:
        data = payload(request, maximum=700000)
        if data.get("operation") == "start":
            _, ready = readiness()
            if not ready:
                return JsonResponse({"ok": False, "message": "Máy nhận diện chưa sẵn sàng. Vui lòng liên hệ quản lý."}, status=503)
            challenge = services.begin_challenge(action=data.get("action"), **source)
            return JsonResponse({"ok": True, "recorded": False, "id": str(challenge.pk), "step": 0,
                **pose_feedback(0, challenge.poses[0])})
        if data.get("operation") != "frame":
            raise ValidationError("Thao tác camera không hợp lệ.")
        try:
            from uuid import UUID
            challenge_id = UUID(str(data.get("id")))
        except ValueError:
            raise ValidationError("Lượt xác minh không hợp lệ.") from None
        return JsonResponse(services.process_frame(challenge_id=challenge_id, frame=data.get("frame"), **source))
    except PermissionDenied:
        return JsonResponse({"ok": False, "done": True, "recorded": False, "message": "Phiên chấm công không còn hiệu lực. Hãy tải lại trang."}, status=403)
    except ValidationError as error:
        return JsonResponse({"ok": False, "message": " ".join(error.messages)}, status=400)
