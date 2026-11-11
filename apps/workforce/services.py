"""Serialize workforce writes with the existing HR lock; re-read every actor/device."""
from datetime import datetime, timedelta
import hashlib
import secrets
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.conf import settings
from django.contrib.sessions.models import Session
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, transaction, models
from django.utils import timezone
from django.utils.crypto import salted_hmac

from apps.employees.models import EmployeeProfile, EmploymentStatus
from core.permissions import can_manage_accounts
from .models import Attendance, AttendanceLog, FaceChallenge, FaceProfile, KioskDevice, WorkSchedule, WorkShift

COOKIE_NAME = "qlnh_attendance_device"


def workforce_lock():
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [81723001])


def manager(actor):
    workforce_lock()
    current = get_user_model().objects.filter(pk=getattr(actor, "pk", None)).first()
    if not can_manage_accounts(current):
        raise PermissionDenied("Chỉ quản lý được thực hiện thao tác này.")
    return current


def employee_ready(employee_id):
    employee = EmployeeProfile.objects.select_related("user", "job_position").get(pk=employee_id)
    if employee.employment_status != EmploymentStatus.WORKING or not employee.user.is_active or not employee.job_position.is_active:
        raise ValidationError("Nhân viên hoặc vị trí công việc không còn hoạt động.")
    return employee


def log(action, description, *, actor=None, schedule=None, device=None):
    AttendanceLog.objects.create(action=action, description=description, actor=actor, schedule=schedule, device=device)


@transaction.atomic
def save_shift(*, actor, data, shift_id=None):
    actor = manager(actor)
    shift = WorkShift.objects.get(pk=shift_id) if shift_id else WorkShift()
    for field in ("code", "name", "starts_at", "ends_at", "break_minutes", "grace_minutes", "is_active"):
        setattr(shift, field, data[field])
    shift.code = shift.code.strip().upper()
    shift.full_clean()
    shift.save()
    log("SHIFT_SAVE", f"Lưu ca {shift.code}: {shift.name}.", actor=actor)
    return shift


@transaction.atomic
def assign_schedule(*, actor, employee_id, shift_id, work_date, note=""):
    actor = manager(actor)
    employee = employee_ready(employee_id)
    shift = WorkShift.objects.get(pk=shift_id)
    if not shift.is_active:
        raise ValidationError("Ca đã ngừng sử dụng.")
    if work_date < timezone.localdate() or work_date < employee.join_date:
        raise ValidationError("Chỉ phân ca từ hôm nay và từ ngày nhân viên vào làm.")
    start = timezone.make_aware(datetime.combine(work_date, shift.starts_at))
    end = timezone.make_aware(datetime.combine(work_date, shift.ends_at))
    if end <= start:
        end += timedelta(days=1)
    if WorkSchedule.objects.filter(employee=employee, starts_at__lt=end, ends_at__gt=start).exclude(status=WorkSchedule.Status.CANCELLED).exists():
        raise ValidationError("Nhân viên đã có ca trùng khoảng thời gian này (kể cả lịch nháp/ca qua đêm).")
    schedule = WorkSchedule(employee=employee, shift=shift, work_date=work_date, starts_at=start, ends_at=end,
                            shift_name=shift.name, break_minutes=shift.break_minutes, grace_minutes=shift.grace_minutes,
                            note=note.strip(), created_by=actor)
    schedule.full_clean()
    schedule.save()
    log("ASSIGN", f"Phân ca {shift.name} cho {employee.employee_code} ngày {work_date}.", actor=actor, schedule=schedule)
    return schedule


@transaction.atomic
def change_schedule(*, actor, schedule_id, revision, action):
    actor = manager(actor)
    schedule = WorkSchedule.objects.select_for_update().get(pk=schedule_id)
    if schedule.revision != revision:
        raise ValidationError("Lịch đã thay đổi. Hãy tải lại trang.")
    if Attendance.objects.filter(schedule=schedule).exists():
        raise ValidationError("Lịch đã có công; hãy điều chỉnh công, không thay đổi lịch.")
    if action == "publish" and schedule.status == WorkSchedule.Status.DRAFT:
        employee_ready(schedule.employee_id)
        if schedule.ends_at <= timezone.now():
            raise ValidationError("Ca đã kết thúc, không thể công bố.")
        schedule.status = WorkSchedule.Status.PUBLISHED
    elif action == "cancel" and schedule.status != WorkSchedule.Status.CANCELLED:
        schedule.status = WorkSchedule.Status.CANCELLED
    else:
        raise ValidationError("Thao tác không phù hợp với trạng thái lịch.")
    schedule.revision += 1
    schedule.save(update_fields=("status", "revision"))
    log("SCHEDULE_STATE", schedule.get_status_display(), actor=actor, schedule=schedule)


def validate_times(schedule, checked_in, checked_out):
    if checked_out and (not checked_in or checked_out <= checked_in):
        raise ValidationError("Giờ ra phải sau giờ vào.")
    now = timezone.now()
    for value in (checked_in, checked_out):
        if value and (timezone.is_naive(value) or value > now or value < schedule.starts_at - timedelta(hours=1) or value > schedule.ends_at + timedelta(hours=4)):
            raise ValidationError("Giờ công phải nằm trong khoảng 1 giờ trước đến 4 giờ sau ca và không ở tương lai.")


@transaction.atomic
def review_attendance(*, actor, schedule_id, revision, action, checked_in=None, checked_out=None, reason=""):
    actor = manager(actor)
    schedule = WorkSchedule.objects.select_for_update().get(pk=schedule_id)
    if schedule.status != WorkSchedule.Status.PUBLISHED:
        raise ValidationError("Chỉ xử lý công cho lịch đã công bố.")
    attendance = Attendance.objects.filter(schedule=schedule).first()
    if (attendance.revision if attendance else 0) != revision:
        raise ValidationError("Bảng công đã thay đổi. Hãy tải lại trang.")
    if schedule.employee.user_id == actor.pk:
        raise PermissionDenied("Công của chính mình cần một quản lý khác xử lý.")
    if action == "reopen":
        if not attendance or attendance.review != Attendance.Review.APPROVED or not reason.strip():
            raise ValidationError("Chỉ mở lại công đã duyệt và phải nhập lý do.")
        attendance.review = Attendance.Review.PENDING
        attendance.approved_by = None
        attendance.approved_at = None
    elif action == "correct":
        if attendance and attendance.review == Attendance.Review.APPROVED:
            raise ValidationError("Công đã duyệt. Hãy mở lại trước khi điều chỉnh.")
        if not reason.strip():
            raise ValidationError("Điều chỉnh hoặc ghi vắng phải có lý do.")
        if not checked_in and schedule.ends_at > timezone.now():
            raise ValidationError("Chỉ ghi vắng sau khi ca kết thúc.")
        validate_times(schedule, checked_in, checked_out)
        attendance = attendance or Attendance(schedule=schedule, revision=0)
        attendance.checked_in_at, attendance.checked_out_at = checked_in, checked_out
        attendance.note = reason.strip()
    elif action == "approve":
        if not attendance or attendance.review == Attendance.Review.APPROVED:
            raise ValidationError("Chưa có công để duyệt hoặc công đã được duyệt.")
        if schedule.ends_at > timezone.now():
            raise ValidationError("Chỉ duyệt sau khi ca kết thúc.")
        if attendance.checked_in_at and not attendance.checked_out_at:
            raise ValidationError("Còn thiếu giờ ra. Hãy bổ sung trước khi duyệt.")
        if not attendance.checked_in_at and not attendance.note:
            raise ValidationError("Công vắng phải có lý do.")
        attendance.review = Attendance.Review.APPROVED
        attendance.approved_by = actor
        attendance.approved_at = timezone.now()
    else:
        raise ValidationError("Thao tác không hợp lệ.")
    before = Attendance.objects.filter(pk=attendance.pk).values("checked_in_at", "checked_out_at", "review").first()
    attendance.revision += 1
    attendance.full_clean()
    attendance.save()
    log("ATTENDANCE_" + action.upper(), f"Trước: {before}; sau: vào={attendance.checked_in_at}, ra={attendance.checked_out_at}, duyệt={attendance.review}. Lý do: {reason.strip()}", actor=actor, schedule=schedule)
    return attendance


def token_digest(raw):
    return hashlib.sha256(raw.encode()).hexdigest()


def get_device(raw):
    if not isinstance(raw, str) or len(raw) != 64:
        raise PermissionDenied("Máy chưa được kích hoạt hoặc đã hết hạn.")
    device = KioskDevice.objects.filter(token_hash=token_digest(raw), is_active=True, expires_at__gt=timezone.now()).first()
    if not device:
        raise PermissionDenied("Máy chưa được kích hoạt hoặc đã bị thu hồi.")
    return device


def shared_session_digest(session_key):
    if not isinstance(session_key, str) or not 32 <= len(session_key) <= 64:
        raise PermissionDenied("Hãy mở lại trang Chấm công để bắt đầu lượt mới.")
    if not Session.objects.filter(session_key=session_key, expire_date__gt=timezone.now()).exists():
        raise PermissionDenied("Phiên chấm công đã hết hạn. Hãy tải lại trang.")
    return salted_hmac("workforce.shared_point", session_key, algorithm="sha256").hexdigest()


def challenge_source(raw_token, session_key):
    if raw_token and session_key:
        raise PermissionDenied("Nguồn chấm công không hợp lệ.")
    if session_key:
        return None, shared_session_digest(session_key)
    return get_device(raw_token), ""


@transaction.atomic
def activate_device(*, actor, name, previous_token=""):
    actor = manager(actor)
    if not name.strip() or len(name) > 100:
        raise ValidationError("Tên máy không hợp lệ.")
    if previous_token:
        KioskDevice.objects.filter(token_hash=token_digest(previous_token)).update(is_active=False)
    raw = secrets.token_hex(32)
    device = KioskDevice.objects.create(name=name.strip(), token_hash=token_digest(raw), expires_at=timezone.now() + timedelta(days=30), created_by=actor)
    log("DEVICE_ACTIVATE", f"Kích hoạt máy {device.name} trong 30 ngày.", actor=actor, device=device)
    return device, raw


@transaction.atomic
def revoke_device(*, actor, device_id):
    actor = manager(actor)
    device = KioskDevice.objects.get(pk=device_id)
    device.is_active = False
    device.save(update_fields=("is_active",))
    log("DEVICE_REVOKE", f"Thu hồi máy {device.name}.", actor=actor, device=device)


def clock_target(employee, action, now):
    """Read eligibility before requesting movement, and recheck when recording."""
    schedules = WorkSchedule.objects.select_for_update().filter(employee=employee, status=WorkSchedule.Status.PUBLISHED)
    if action == "IN":
        candidates = list(schedules.filter(starts_at__lte=now + timedelta(hours=1), ends_at__gt=now))
        # At adjacent shifts, a clocked-in previous shift must be closed first.
        if Attendance.objects.filter(schedule__employee=employee, checked_in_at__isnull=False, checked_out_at__isnull=True).exists():
            raise ValidationError("Bạn còn ca chưa ra. Hãy chọn Ra ca hoặc nhờ quản lý xử lý.", code="open_shift")
        candidates = [s for s in candidates if not Attendance.objects.filter(schedule=s).exists()]
        if not candidates:
            upcoming = schedules.filter(starts_at__gt=now).order_by("starts_at").first()
            if upcoming:
                local_start = timezone.localtime(upcoming.starts_at)
                raise ValidationError(f"Ca tiếp theo bắt đầu lúc {local_start:%H:%M ngày %d/%m}. Chỉ vào ca từ 60 phút trước giờ bắt đầu.", code="outside_window")
            draft = WorkSchedule.objects.filter(employee=employee, status=WorkSchedule.Status.DRAFT, starts_at__lte=now+timedelta(hours=1), ends_at__gt=now).exists()
            if draft:
                raise ValidationError("Lịch ca hiện còn là bản nháp. Nhờ quản lý công bố lịch trước khi chấm công.", code="draft_shift")
            already = Attendance.objects.filter(schedule__in=schedules.filter(starts_at__lte=now+timedelta(hours=1), ends_at__gt=now)).exists()
            if already:
                raise ValidationError("Ca này đã có bản ghi công. Kiểm tra bảng công hoặc nhờ quản lý điều chỉnh.", code="already_recorded")
            raise ValidationError("Chưa có lịch ca đã công bố phù hợp với giờ hiện tại. Nhờ quản lý phân và công bố ca trước khi chấm công.", code="no_schedule")
        if len(candidates) > 1:
            raise ValidationError("Có nhiều ca gần nhau cùng được phép vào. Nhờ quản lý kiểm tra lịch.", code="ambiguous_shift")
        return candidates[0], None
    elif action == "OUT":
        rows = list(Attendance.objects.select_related("schedule").filter(schedule__in=schedules, checked_in_at__isnull=False,
                    checked_out_at__isnull=True, review=Attendance.Review.PENDING, schedule__ends_at__gte=now-timedelta(hours=4)))
        if len(rows) != 1:
            raise ValidationError("Chưa có giờ vào ca đang mở, hoặc đã quá 4 giờ sau ca. Nhờ quản lý kiểm tra bảng công.", code="no_open_shift")
        attendance = rows[0]
        schedule = attendance.schedule
        if now <= attendance.checked_in_at:
            raise ValidationError("Giờ ra phải sau giờ vào.")
        return schedule, attendance
    else:
        raise ValidationError("Chọn Vào ca hoặc Ra ca.")


def automatic_clock_action(employee, now):
    """Resolve from the ledger under workforce_lock; debounce across devices."""
    recent = Attendance.objects.filter(schedule__employee=employee).filter(
        models.Q(checked_in_at__gte=now-timedelta(seconds=60)) |
        models.Q(checked_out_at__gte=now-timedelta(seconds=60))).exists()
    if recent:
        raise ValidationError("Bạn vừa chấm công thành công. Vui lòng chờ ít nhất 60 giây trước lượt tiếp theo; kiểm tra bảng công nếu cần.", code="recent_clock")
    return "OUT" if Attendance.objects.filter(schedule__employee=employee,
        checked_in_at__isnull=False, checked_out_at__isnull=True).exists() else "IN"


@transaction.atomic
def record_clock(*, employee_id, action, device=None, session_key=None):
    workforce_lock()
    now = timezone.now()
    if device is not None:
        if session_key or not KioskDevice.objects.filter(pk=device.pk, is_active=True, expires_at__gt=now).exists():
            raise PermissionDenied("Thiết bị đã bị thu hồi.")
    else:
        shared_session_digest(session_key)
    employee = employee_ready(employee_id)
    schedule, attendance = clock_target(employee, action, now)
    if action == "IN":
        attendance = Attendance.objects.create(schedule=schedule, checked_in_at=now)
    else:
        attendance.checked_out_at = now
        attendance.revision += 1
        attendance.save(update_fields=("checked_out_at", "revision"))
    source = "trang chấm công chung" if device is None else "thiết bị đã kích hoạt"
    log("FACE_" + action, f"{employee.employee_code}: {'vào' if action == 'IN' else 'ra'} ca bằng khuôn mặt tại {source}.", schedule=schedule, device=device)
    return attendance


@transaction.atomic
def enroll_face(*, actor, employee_id, frames, consent):
    from .face import extract_frame, cosine, best_match, MODEL_VERSION
    actor = manager(actor)
    employee = employee_ready(employee_id)
    if consent is not True or not isinstance(frames, list) or len(frames) != 3:
        raise ValidationError("Cần xác nhận đồng ý và chụp đủ 3 mẫu khuôn mặt.")
    samples = [extract_frame(frame) for frame in frames]
    if len({sample["hash"] for sample in samples}) != 3:
        raise ValidationError("Ba ảnh phải được chụp riêng, không dùng lại một ảnh.")
    vectors = [sample["vector"] for sample in samples]
    if any(cosine(vectors[0], v) < 0.45 for v in vectors[1:]):
        raise ValidationError("Các mẫu không nhất quán. Hãy chụp lại cùng một nhân viên.")
    if best_match(vectors[0], FaceProfile.objects.exclude(employee=employee), threshold=0.45, margin=0):
        raise ValidationError("Khuôn mặt gần trùng hồ sơ nhân viên khác. Hãy kiểm tra trước khi đăng ký.")
    profile, _ = FaceProfile.objects.update_or_create(employee=employee, defaults={"embeddings": vectors,
        "model_version": MODEL_VERSION, "consent_at": timezone.now(), "enrolled_by": actor})
    log("FACE_ENROLL", f"Đăng ký lại 3 mẫu khuôn mặt cho {employee.employee_code}; đã xác nhận đồng ý.", actor=actor)
    return profile


@transaction.atomic
def delete_face(*, actor, employee_id):
    actor = manager(actor)
    employee = EmployeeProfile.objects.get(pk=employee_id)
    FaceProfile.objects.filter(employee=employee).delete()
    FaceChallenge.objects.filter(employee=employee, used_at__isnull=True).update(used_at=timezone.now())
    log("FACE_DELETE", f"Xóa mẫu khuôn mặt của {employee.employee_code}.", actor=actor)


@transaction.atomic
def begin_challenge(*, action, raw_token=None, session_key=None):
    workforce_lock()
    device, digest = challenge_source(raw_token, session_key)
    if action not in ("AUTO", "IN", "OUT"):
        raise ValidationError("Chọn Vào ca hoặc Ra ca.")
    now = timezone.now()
    source_rows = FaceChallenge.objects.filter(device=device, session_digest=digest)
    latest = source_rows.order_by("-created_at").first()
    if latest and now - latest.created_at < timedelta(seconds=3):
        raise ValidationError("Vui lòng chờ vài giây trước khi thử lại.")
    # Bound history without keeping camera images or templates in challenge rows.
    FaceChallenge.objects.filter(expires_at__lt=now-timedelta(days=1)).delete()
    source_rows.filter(used_at__isnull=True).update(used_at=now)
    return FaceChallenge.objects.create(id=uuid4(), device=device, session_digest=digest, action=action, is_automatic=action=="AUTO",
        poses=["CENTER", secrets.choice(("LEFT", "RIGHT")), "CENTER"], expires_at=now+timedelta(seconds=90))


@transaction.atomic
def process_frame(*, challenge_id, frame, raw_token=None, session_key=None):
    from .face import extract_frame, best_match, pose_matches, pose_feedback, MODEL_VERSION
    workforce_lock()
    device, digest = challenge_source(raw_token, session_key)
    challenge = FaceChallenge.objects.select_for_update().filter(pk=challenge_id, device=device, session_digest=digest).first()
    now = timezone.now()
    if not challenge or challenge.used_at or challenge.expires_at <= now:
        raise ValidationError("Lượt xác minh đã hết hạn hoặc đã sử dụng. Hãy bắt đầu lại.")
    if challenge.last_attempt_at and now - challenge.last_attempt_at < timedelta(milliseconds=600):
        raise ValidationError("Hãy giữ tư thế một chút trước khi chụp tiếp.")
    challenge.attempts += 1
    challenge.last_attempt_at = now
    if challenge.attempts > 24:
        challenge.used_at = now
        challenge.save()
        return {"ok": False, "done": True, "message": "Đã thử quá nhiều lần. Hãy bắt đầu lại."}
    identified_name = None
    recognition = {}
    feedback = {}
    try:
        sample = extract_frame(frame)
        if sample["hash"] in challenge.frame_hashes:
            raise ValidationError("Ảnh bị lặp. Hãy đứng trước camera và chụp lại.")
        profiles = FaceProfile.objects.select_related("employee").filter(model_version=MODEL_VERSION,
            employee__employment_status=EmploymentStatus.WORKING, employee__user__is_active=True, employee__job_position__is_active=True)
        match = best_match(sample["vector"], profiles)
        if not match:
            raise ValidationError("Chưa thấy rõ khuôn mặt đã đăng ký. Đưa mặt về khung, quay nhẹ và giữ yên.", code="face_not_matched")
        profile = match[0]
        if challenge.employee_id and (profile.employee_id != challenge.employee_id or profile.updated_at != challenge.profile_version):
            challenge.used_at = now
            raise ValidationError("Người chấm công hoặc hồ sơ đã thay đổi. Hãy bắt đầu lại.")
        identified_name = profile.employee.full_name
        recognition = {"employee_code": profile.employee.employee_code, "similarity": round(match[1], 4),
            "threshold": settings.ATTENDANCE_FACE_THRESHOLD}
        if challenge.is_automatic:
            try:
                resolved = automatic_clock_action(profile.employee, now)
            except ValidationError:
                challenge.used_at = now
                raise
            if challenge.action != "AUTO" and challenge.action != resolved:
                challenge.used_at = now
                raise ValidationError("Giờ công đã thay đổi trong lúc xác minh. Kiểm tra bảng công rồi bắt đầu lại.", code="clock_changed")
            challenge.action = resolved
            challenge.employee = profile.employee
            challenge.profile_version = profile.updated_at
        # Explain schedule problems immediately after identifying the face.
        try:
            schedule, _ = clock_target(profile.employee, challenge.action, now)
        except ValidationError:
            challenge.used_at = now
            raise
        if challenge.step and challenge.neutral_yaw is None:
            challenge.used_at = now
            raise ValidationError("Lượt xác minh cũ đã thay đổi. Bấm Chấm công để bắt đầu lại.", code="restart")
        expected_pose = challenge.poses[challenge.step]
        feedback = pose_feedback(sample["yaw"], expected_pose, challenge.neutral_yaw)
        if not pose_matches(sample["yaw"], expected_pose, challenge.neutral_yaw):
            raise ValidationError(feedback["instruction"], code="pose_mismatch")
        if challenge.step == 0:
            challenge.neutral_yaw = sample["yaw"]
        challenge.employee = profile.employee
        challenge.profile_version = profile.updated_at
        challenge.frame_hashes = [*challenge.frame_hashes, sample["hash"]]
        challenge.step += 1
        if challenge.step == len(challenge.poses):
            if now - challenge.created_at < timedelta(seconds=2):
                raise ValidationError("Thao tác quá nhanh. Hãy thử lại.")
            # A savepoint ensures a failed clock cannot leave a partial record.
            with transaction.atomic():
                attendance = record_clock(employee_id=profile.employee_id, action=challenge.action, device=device, session_key=session_key)
            challenge.used_at = now
            challenge.save()
            return {"ok": True, "done": True, "recorded": True, "identified": True, "name": profile.employee.full_name,
                    "message": f"{'Vào ca' if challenge.action == 'IN' else 'Ra ca'} thành công lúc {timezone.localtime(now):%H:%M:%S}.",
                    "shift": attendance.schedule.shift_name, "action": challenge.action, "recorded_at": now.isoformat(), **recognition}
        challenge.save()
        return {"ok": True, "done": False, "recorded": False, "identified": True, "name": profile.employee.full_name,
                "pose": challenge.poses[challenge.step], "step": challenge.step, "shift": schedule.shift_name,
                "action": challenge.action, **recognition, **pose_feedback(sample["yaw"], challenge.poses[challenge.step], challenge.neutral_yaw)}
    except ValidationError as error:
        if challenge.step >= len(challenge.poses):
            challenge.used_at = now
        challenge.save()
        code = getattr(error, "code", None) or getattr(error.error_list[0], "code", None) or "camera"
        return {"ok": False, "done": bool(challenge.used_at), "recorded": False, "identified": bool(identified_name),
                "name": identified_name, "code": code, "step": min(challenge.step, 2),
                "message": " ".join(error.messages), "action": challenge.action, **recognition, **feedback}
