from datetime import datetime, time, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.employees.models import EmployeeProfile, EmploymentStatus, JobPosition
from apps.workforce import services
from apps.workforce.face import MODEL_VERSION, best_match, extract_frame, normalize, pose_matches
from apps.workforce.models import Attendance, AttendanceLog, FaceChallenge, FaceProfile, KioskDevice, WorkSchedule, WorkShift


def fixtures():
    User = get_user_model()
    group, _ = Group.objects.get_or_create(name="WF_TEST")
    position, _ = JobPosition.objects.get_or_create(code="WF_TEST", defaults={"name": "Kiểm thử ca làm", "group": group})
    manager = User.objects.create_user(username="wf_manager", is_superuser=True, is_staff=True)
    user = User.objects.create_user(username="wf_employee")
    employee = EmployeeProfile.objects.create(user=user, employee_code="WF001", full_name="Nhân viên kiểm thử", phone="0919000011", join_date=timezone.localdate(), job_position=position)
    other_user = User.objects.create_user(username="wf_other")
    other = EmployeeProfile.objects.create(user=other_user, employee_code="WF002", full_name="Nhân viên khác", phone="0919000012", join_date=timezone.localdate(), job_position=position)
    shift = WorkShift.objects.create(code="SANG", name="Ca sáng", starts_at=time(8), ends_at=time(14), break_minutes=30, grace_minutes=5)
    device = KioskDevice.objects.create(name="Cửa chính", token_hash=services.token_digest("a"*64), expires_at=timezone.now()+timedelta(days=30), created_by=manager)
    return manager, user, employee, other, shift, device


def vector(index=0):
    result = [0.0]*128
    result[index] = 1.0
    return result


class WorkforceFixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager, cls.user, cls.employee, cls.other, cls.shift, cls.device = fixtures()
        cls.day = timezone.localdate()+timedelta(days=1)

    def schedule(self, employee=None, shift=None, day=None, publish=True):
        row = services.assign_schedule(actor=self.manager, employee_id=(employee or self.employee).pk, shift_id=(shift or self.shift).pk, work_date=day or self.day)
        if publish:
            services.change_schedule(actor=self.manager, schedule_id=row.pk, revision=row.revision, action="publish")
            row.refresh_from_db()
        return row

    def at(self, moment):
        return patch("apps.workforce.services.timezone.now", return_value=moment)


class WorkforceTests(WorkforceFixture):
    def test_overnight_overlap_rejected_but_adjacent_allowed(self):
        night = WorkShift.objects.create(code="DEM", name="Ca đêm", starts_at=time(22), ends_at=time(6))
        row = self.schedule(shift=night)
        self.assertEqual(timezone.localtime(row.ends_at).date(), timezone.localtime(row.starts_at).date()+timedelta(days=1))
        morning = WorkShift.objects.create(code="SOM", name="Ca sớm", starts_at=time(5), ends_at=time(8))
        with self.assertRaisesMessage(ValidationError, "trùng"):
            self.schedule(shift=morning, day=self.day+timedelta(days=1))
        morning.starts_at = time(6)
        morning.save()
        self.schedule(shift=morning, day=self.day+timedelta(days=1))

    def test_draft_conflicts_and_cancel_releases_time(self):
        row = self.schedule(publish=False)
        with self.assertRaises(ValidationError):
            self.schedule()
        services.change_schedule(actor=self.manager, schedule_id=row.pk, revision=row.revision, action="cancel")
        self.schedule()

    def test_shift_change_does_not_rewrite_existing_schedule(self):
        row = self.schedule()
        data = {field: getattr(self.shift, field) for field in ("code", "name", "starts_at", "ends_at", "break_minutes", "grace_minutes", "is_active")}
        data["starts_at"] = time(9)
        services.save_shift(actor=self.manager, shift_id=self.shift.pk, data=data)
        row.refresh_from_db()
        self.assertEqual(timezone.localtime(row.starts_at).hour, 8)

    def test_invalid_shift_and_break_rejected(self):
        shift = WorkShift(code="BAD", name="Sai", starts_at=time(8), ends_at=time(8))
        with self.assertRaises(ValidationError):
            shift.full_clean()
        shift.ends_at = time(14)
        shift.break_minutes = 360
        with self.assertRaises(ValidationError):
            shift.full_clean()

    def test_disabled_or_resigned_employee_cannot_be_assigned(self):
        self.user.is_active = False
        self.user.save()
        with self.assertRaises(ValidationError):
            self.schedule()

    def test_stale_actor_permission_and_revision_rejected(self):
        with self.assertRaises(PermissionDenied):
            services.assign_schedule(actor=self.user, employee_id=self.employee.pk, shift_id=self.shift.pk, work_date=self.day)
        row = self.schedule()
        with self.assertRaises(ValidationError):
            services.change_schedule(actor=self.manager, schedule_id=row.pk, revision=1, action="cancel")
        get_user_model().objects.filter(pk=self.manager.pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            services.change_schedule(actor=self.manager, schedule_id=row.pk, revision=row.revision, action="cancel")

    def test_face_clock_records_late_early_and_clamped_minutes(self):
        row = self.schedule()
        with self.at(row.starts_at+timedelta(minutes=12)):
            attendance = services.record_clock(employee_id=self.employee.pk, action="IN", device=self.device)
        with self.at(row.ends_at-timedelta(minutes=10)):
            attendance = services.record_clock(employee_id=self.employee.pk, action="OUT", device=self.device)
        self.assertEqual(attendance.late_minutes, 12)
        self.assertEqual(attendance.early_minutes, 10)
        self.assertEqual(attendance.worked_minutes, 308)
        self.assertTrue(attendance.is_late)

    def test_early_in_late_out_does_not_create_overtime(self):
        row = self.schedule()
        with self.at(row.starts_at-timedelta(minutes=20)):
            services.record_clock(employee_id=self.employee.pk, action="IN", device=self.device)
        with self.at(row.ends_at+timedelta(minutes=20)):
            attendance = services.record_clock(employee_id=self.employee.pk, action="OUT", device=self.device)
        self.assertEqual(attendance.worked_minutes, 330)

    def test_draft_wrong_time_and_duplicate_in_rejected(self):
        row = self.schedule(publish=False)
        with self.at(row.starts_at), self.assertRaises(ValidationError):
            services.record_clock(employee_id=self.employee.pk, action="IN", device=self.device)
        services.change_schedule(actor=self.manager, schedule_id=row.pk, revision=1, action="publish")
        with self.at(row.starts_at-timedelta(hours=2)), self.assertRaises(ValidationError):
            services.record_clock(employee_id=self.employee.pk, action="IN", device=self.device)
        with self.at(row.starts_at):
            services.record_clock(employee_id=self.employee.pk, action="IN", device=self.device)
            with self.assertRaises(ValidationError):
                services.record_clock(employee_id=self.employee.pk, action="IN", device=self.device)
        self.assertEqual(Attendance.objects.count(), 1)

    def test_out_requires_in_and_window_and_active_employee(self):
        row = self.schedule()
        with self.at(row.starts_at), self.assertRaises(ValidationError):
            services.record_clock(employee_id=self.employee.pk, action="OUT", device=self.device)
        with self.at(row.starts_at):
            services.record_clock(employee_id=self.employee.pk, action="IN", device=self.device)
        with self.at(row.ends_at+timedelta(hours=5)), self.assertRaises(ValidationError):
            services.record_clock(employee_id=self.employee.pk, action="OUT", device=self.device)
        EmployeeProfile.objects.filter(pk=self.employee.pk).update(employment_status=EmploymentStatus.RESIGNED)
        with self.at(row.ends_at), self.assertRaises(ValidationError):
            services.record_clock(employee_id=self.employee.pk, action="OUT", device=self.device)

    def test_attended_schedule_cannot_be_cancelled(self):
        row = self.schedule()
        Attendance.objects.create(schedule=row, checked_in_at=row.starts_at)
        with self.assertRaises(ValidationError):
            services.change_schedule(actor=self.manager, schedule_id=row.pk, revision=row.revision, action="cancel")

    def test_correct_approve_lock_reopen_and_audit(self):
        row = self.schedule()
        with self.at(row.ends_at+timedelta(minutes=30)):
            attendance = services.review_attendance(actor=self.manager, schedule_id=row.pk, revision=0, action="correct", checked_in=row.starts_at, checked_out=row.ends_at, reason="Quên chấm công")
            attendance = services.review_attendance(actor=self.manager, schedule_id=row.pk, revision=attendance.revision, action="approve")
            self.assertEqual(attendance.review, "APPROVED")
            with self.assertRaises(ValidationError):
                services.review_attendance(actor=self.manager, schedule_id=row.pk, revision=attendance.revision, action="correct", reason="Sửa")
            attendance = services.review_attendance(actor=self.manager, schedule_id=row.pk, revision=attendance.revision, action="reopen", reason="Đối chiếu lại")
            self.assertEqual(attendance.review, "PENDING")
            self.assertIsNone(attendance.approved_at)
        self.assertTrue(AttendanceLog.objects.filter(action="ATTENDANCE_REOPEN").exists())

    def test_missing_out_future_time_and_own_review_rejected(self):
        row = self.schedule()
        attendance = Attendance.objects.create(schedule=row, checked_in_at=row.starts_at)
        with self.at(row.ends_at+timedelta(minutes=1)):
            with self.assertRaises(ValidationError):
                services.review_attendance(actor=self.manager, schedule_id=row.pk, revision=1, action="approve")
            with self.assertRaises(ValidationError):
                services.review_attendance(actor=self.manager, schedule_id=row.pk, revision=1, action="correct", checked_in=row.starts_at, checked_out=row.ends_at+timedelta(hours=1), reason="Sai giờ")
        WorkSchedule.objects.filter(pk=row.pk).update(employee=self.other)
        get_user_model().objects.filter(pk=self.other.user_id).update(is_superuser=True)
        with self.assertRaises(PermissionDenied):
            services.review_attendance(actor=self.other.user, schedule_id=row.pk, revision=1, action="approve")

    def test_absence_requires_finished_shift_reason_and_approval(self):
        row = self.schedule()
        with self.at(row.starts_at), self.assertRaises(ValidationError):
            services.review_attendance(actor=self.manager, schedule_id=row.pk, revision=0, action="correct", reason="Vắng")
        with self.at(row.ends_at+timedelta(minutes=1)):
            attendance = services.review_attendance(actor=self.manager, schedule_id=row.pk, revision=0, action="correct", reason="Nghỉ có phép")
            attendance = services.review_attendance(actor=self.manager, schedule_id=row.pk, revision=attendance.revision, action="approve")
        self.assertEqual(attendance.condition, "Vắng")
        self.assertEqual(attendance.worked_minutes, 0)

    def test_clock_atomic_if_audit_fails(self):
        row = self.schedule()
        with self.at(row.starts_at), patch("apps.workforce.services.log", side_effect=RuntimeError("audit down")), self.assertRaises(RuntimeError):
            services.record_clock(employee_id=self.employee.pk, action="IN", device=self.device)
        self.assertFalse(Attendance.objects.exists())

    def test_revoked_device_rejected_even_with_stale_device_object(self):
        row = self.schedule()
        services.revoke_device(actor=self.manager, device_id=self.device.pk)
        with self.assertRaises(PermissionDenied):
            services.get_device("a"*64)
        with self.at(row.starts_at), self.assertRaises(PermissionDenied):
            services.record_clock(employee_id=self.employee.pk, action="IN", device=self.device)

    def test_enrollment_checks_consent_consistency_and_duplicate_identity(self):
        samples = [{"hash":str(i), "vector":vector(), "yaw":0} for i in range(3)]
        with patch("apps.workforce.face.extract_frame", side_effect=samples):
            services.enroll_face(actor=self.manager, employee_id=self.employee.pk, frames=["a","b","c"], consent=True)
        with self.assertRaises(ValidationError):
            services.enroll_face(actor=self.manager, employee_id=self.other.pk, frames=["a","b","c"], consent=False)
        with patch("apps.workforce.face.extract_frame", side_effect=samples), self.assertRaises(ValidationError):
            services.enroll_face(actor=self.manager, employee_id=self.other.pk, frames=["a","b","c"], consent=True)

    def test_face_challenge_consumed_only_after_three_poses_and_no_replay(self):
        row = self.schedule()
        FaceProfile.objects.create(employee=self.employee, embeddings=[vector()], consent_at=timezone.now(), enrolled_by=self.manager)
        with self.at(row.starts_at):
            challenge = services.begin_challenge(raw_token="a"*64, action="IN")
        yaw = -.3 if challenge.poses[1] == "LEFT" else .3
        for index, turn in enumerate((0, yaw, 0)):
            with self.at(row.starts_at+timedelta(seconds=3+index*3)), patch("apps.workforce.face.extract_frame", return_value={"hash":str(index), "vector":vector(), "yaw":turn}):
                result = services.process_frame(raw_token="a"*64, challenge_id=challenge.pk, frame="jpeg")
            self.assertTrue(result["ok"])
            self.assertEqual(Attendance.objects.count(), int(index == 2))
        self.assertTrue(result["done"])
        with self.at(row.starts_at+timedelta(seconds=15)), self.assertRaises(ValidationError):
            services.process_frame(raw_token="a"*64, challenge_id=challenge.pk, frame="jpeg")

    def test_challenge_wrong_pose_and_same_frame_never_records_clock(self):
        row = self.schedule()
        FaceProfile.objects.create(employee=self.employee, embeddings=[vector()], consent_at=timezone.now())
        with self.at(row.starts_at):
            challenge = services.begin_challenge(raw_token="a"*64, action="IN")
        for index in range(3):
            with self.at(row.starts_at+timedelta(seconds=3+index*3)), patch("apps.workforce.face.extract_frame", return_value={"hash":"same", "vector":vector(), "yaw":0}):
                result = services.process_frame(raw_token="a"*64, challenge_id=challenge.pk, frame="jpeg")
        challenge.refresh_from_db()
        self.assertEqual(challenge.step, 1)
        self.assertFalse(result["ok"])
        self.assertFalse(Attendance.objects.exists())

    def test_deleted_profile_invalidates_challenge(self):
        FaceProfile.objects.create(employee=self.employee, embeddings=[vector()], consent_at=timezone.now())
        challenge = services.begin_challenge(raw_token="a"*64, action="IN")
        challenge.employee = self.employee
        challenge.save()
        services.delete_face(actor=self.manager, employee_id=self.employee.pk)
        challenge.refresh_from_db()
        self.assertIsNotNone(challenge.used_at)
        self.assertFalse(FaceProfile.objects.exists())

    def test_ambiguous_or_invalid_vectors_rejected(self):
        profile = lambda pk: SimpleNamespace(embeddings=[vector()], model_version=MODEL_VERSION, pk=pk)
        self.assertIsNone(best_match(vector(), [profile(1), profile(2)]))
        self.assertIsNone(best_match(vector(1), [profile(1)]))
        with self.assertRaises(ValidationError):
            normalize([float("nan")]*128)
        with self.assertRaises(ValidationError):
            extract_frame("data:image/jpeg;base64,bm90LWltYWdl")
        self.assertTrue(pose_matches(0, "CENTER"))
        self.assertFalse(pose_matches(0, "LEFT"))

    def test_database_rejects_out_without_in(self):
        row = self.schedule()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Attendance.objects.create(schedule=row, checked_out_at=row.ends_at)


class WorkforceViewTests(WorkforceFixture):
    def test_manager_pages_render_and_staff_permissions(self):
        row = self.schedule()
        self.client.force_login(self.manager)
        with patch("apps.workforce.views.readiness", return_value=("", True)):
            for name in ("schedules", "shifts", "timesheet", "faces", "devices", "mine"):
                response = self.client.get(reverse("workforce:"+name))
                self.assertEqual(response.status_code, 200, name)
            self.assertEqual(self.client.get(reverse("workforce:attendance", args=[row.pk])).status_code, 200)
            self.assertEqual(self.client.get(reverse("workforce:face_enroll", args=[self.employee.pk])).status_code, 200)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("workforce:schedules")).status_code, 403)
        self.assertEqual(self.client.post(reverse("workforce:face_save", args=[self.employee.pk]), data={}, content_type="application/json").status_code, 403)

    def test_personal_schedule_hides_others_and_drafts(self):
        self.schedule()
        self.schedule(employee=self.other)
        self.schedule(day=self.day+timedelta(days=1), publish=False)
        self.client.force_login(self.user)
        query = {"start": self.day, "end": self.day+timedelta(days=1)}
        response = self.client.get(reverse("workforce:mine"), query)
        self.assertContains(response, self.shift.name, count=1)
        self.assertNotContains(response, self.other.full_name)

    def test_bulk_assignment_rolls_back_when_one_employee_conflicts(self):
        self.schedule(employee=self.other)
        self.client.force_login(self.manager)
        response = self.client.post(reverse("workforce:schedules"), {"employees":[self.employee.pk,self.other.pk], "shift":self.shift.pk, "work_date":self.day})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(WorkSchedule.objects.filter(employee=self.employee).exists())

    def test_device_activation_logs_out_manager_and_uses_scoped_http_only_cookie(self):
        self.client.force_login(self.manager)
        response = self.client.post(reverse("workforce:devices"), {"name":"Cửa chính", "confirm":"on"}, secure=True)
        self.assertRedirects(response, reverse("workforce:kiosk"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)
        cookie = response.cookies[services.COOKIE_NAME]
        self.assertTrue(cookie["httponly"])
        self.assertTrue(cookie["secure"])
        self.assertEqual(cookie["path"], "/cham-cong/kiosk/")
        self.assertEqual(cookie["samesite"], "Strict")
        self.assertEqual(self.client.get(reverse("workforce:kiosk"), secure=True).status_code, 200)
        self.assertEqual(self.client.get(reverse("workforce:schedules"), secure=True).status_code, 302)

    def test_kiosk_requires_device_and_csrf_and_rejects_invalid_payload(self):
        endpoint = reverse("workforce:kiosk_api")
        self.assertEqual(self.client.get(endpoint).status_code, 405)
        self.assertEqual(self.client.post(endpoint, data={"operation":"start", "action":"IN"}, content_type="application/json").status_code, 403)
        client = Client(enforce_csrf_checks=True)
        client.cookies[services.COOKIE_NAME] = "a"*64
        client.get(reverse("workforce:kiosk"))
        self.assertEqual(client.post(endpoint, data={}, content_type="application/json").status_code, 403)
        response = client.post(endpoint, data=[], content_type="application/json", HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value)
        self.assertEqual(response.status_code, 400)

    def test_csv_counts_only_approved_work_and_escapes_formula_names(self):
        row = self.schedule()
        EmployeeProfile.objects.filter(pk=self.employee.pk).update(full_name="=1+1")
        Attendance.objects.create(schedule=row, checked_in_at=row.starts_at, checked_out_at=row.ends_at)
        self.client.force_login(self.manager)
        response = self.client.get(reverse("workforce:timesheet"), {"start":self.day,"end":self.day,"export":"csv"})
        self.assertContains(response, "'=1+1")
        self.assertIn(",1,0,0,0,0,0", response.content.decode("utf-8-sig"))
