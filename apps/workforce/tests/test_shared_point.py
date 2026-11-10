from datetime import timedelta
from unittest.mock import patch
from django.contrib.sessions.backends.cached_db import SessionStore
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.workforce import services
from apps.workforce.face import pose_feedback, pose_matches
from apps.workforce.models import Attendance, FaceChallenge, FaceProfile, KioskDevice
from .test_workforce import WorkforceFixture, vector


def new_session():
    session = SessionStore()
    session["attendance_point"] = True
    session.create()
    return session.session_key


class SharedPointTests(WorkforceFixture):
    def enroll(self):
        return FaceProfile.objects.create(employee=self.employee, embeddings=[vector()], consent_at=timezone.now())

    def frame(self, challenge, moment, yaw, fingerprint="frame", session_key=None):
        source = {"session_key": session_key} if session_key else {"raw_token":"a"*64}
        with self.at(moment), patch("apps.workforce.face.extract_frame", return_value={"hash":fingerprint, "vector":vector(), "yaw":yaw}):
            return services.process_frame(challenge_id=challenge.pk, frame="jpeg", **source)

    def test_relative_turn_works_for_off_center_neutral_face(self):
        row = self.schedule()
        self.enroll()
        session_key = new_session()
        with self.at(row.starts_at):
            challenge = services.begin_challenge(session_key=session_key, action="IN")
        # This person's nose/eye neutral offset would fail the old fixed .16 rule.
        turn = .23 + (-.13 if challenge.poses[1] == "LEFT" else .13)
        for index, yaw in enumerate((.23, turn, .25)):
            result = self.frame(challenge, row.starts_at+timedelta(seconds=3+index*3), yaw, str(index), session_key)
            self.assertTrue(result["ok"], result)
            self.assertEqual(Attendance.objects.count(), int(index==2))
        self.assertTrue(result["recorded"])
        self.assertTrue(result["done"])
        self.assertIsNone(Attendance.objects.get().schedule.attendance.approved_at)

    def test_identified_face_without_schedule_reports_reason_immediately(self):
        self.enroll()
        key = new_session()
        challenge = services.begin_challenge(session_key=key, action="IN")
        result = self.frame(challenge, timezone.now()+timedelta(seconds=3), 0, session_key=key)
        self.assertTrue(result["identified"])
        self.assertEqual(result["name"], self.employee.full_name)
        self.assertEqual(result["code"], "no_schedule")
        self.assertTrue(result["done"])
        self.assertFalse(result["recorded"])
        self.assertFalse(Attendance.objects.exists())

    def test_draft_schedule_explains_publish_requirement(self):
        row = self.schedule(publish=False)
        self.enroll()
        with self.at(row.starts_at):
            challenge = services.begin_challenge(raw_token="a"*64, action="IN")
        result = self.frame(challenge, row.starts_at+timedelta(seconds=3), 0)
        self.assertEqual(result["code"], "draft_shift")
        self.assertIn("công bố", result["message"])
        self.assertTrue(result["done"])

    def test_wrong_turn_retains_identity_and_gives_directional_feedback(self):
        row = self.schedule()
        self.enroll()
        with self.at(row.starts_at):
            challenge = services.begin_challenge(raw_token="a"*64, action="IN")
        self.frame(challenge, row.starts_at+timedelta(seconds=3), .2, "first")
        wrong = .4 if challenge.poses[1] == "LEFT" else 0
        result = self.frame(challenge, row.starts_at+timedelta(seconds=6), wrong, "second")
        self.assertEqual(result["code"], "pose_mismatch")
        self.assertTrue(result["identified"])
        self.assertFalse(result["done"])
        self.assertIn("ngược hướng", result["instruction"])
        self.assertEqual(result["movement"], 0)
        self.assertEqual(result["step"], 1)

    def test_sessions_cannot_replay_or_cancel_each_others_challenges(self):
        first, second = new_session(), new_session()
        one = services.begin_challenge(session_key=first, action="IN")
        two = services.begin_challenge(session_key=second, action="IN")
        one.refresh_from_db()
        self.assertIsNone(one.used_at)
        self.assertNotEqual(one.session_digest, two.session_digest)
        self.assertNotIn(first, one.session_digest)
        with self.assertRaises(ValidationError):
            services.process_frame(session_key=second, challenge_id=one.pk, frame="jpeg")
        with self.assertRaises(PermissionDenied):
            services.begin_challenge(session_key="x"*32, action="IN")

    def test_expired_challenge_and_identity_change_do_not_record(self):
        row = self.schedule()
        profile = self.enroll()
        with self.at(row.starts_at):
            challenge = services.begin_challenge(raw_token="a"*64, action="IN")
        self.frame(challenge, row.starts_at+timedelta(seconds=3), 0, "first")
        FaceProfile.objects.filter(pk=profile.pk).update(updated_at=row.starts_at+timedelta(seconds=4))
        result = self.frame(challenge, row.starts_at+timedelta(seconds=6), .3, "second")
        self.assertTrue(result["done"])
        self.assertFalse(result["recorded"])
        self.assertFalse(Attendance.objects.exists())
        with self.at(row.starts_at+timedelta(seconds=100)), self.assertRaises(ValidationError):
            services.process_frame(raw_token="a"*64, challenge_id=challenge.pk, frame="jpeg")

    def test_point_is_public_without_device_activation_but_admin_stays_protected(self):
        count = KioskDevice.objects.count()
        client = Client(enforce_csrf_checks=True)
        endpoint = reverse("workforce:point_api")
        self.assertEqual(client.post(endpoint, data={}, content_type="application/json").status_code, 403)
        response = client.get(reverse("workforce:point"))
        self.assertContains(response, "Trang chấm công chung")
        self.assertNotContains(response, "Kích hoạt")
        self.assertTrue(client.session.get("attendance_point"))
        self.assertNotIn("_auth_user_id", client.session)
        self.assertEqual(KioskDevice.objects.count(), count)
        self.assertEqual(client.get(reverse("workforce:schedules")).status_code, 302)
        self.assertEqual(client.post(endpoint, data={}, content_type="application/json").status_code, 403)
        with patch("apps.workforce.views.readiness", return_value=("",True)):
            response = client.post(endpoint, data={"operation":"start", "action":"IN"}, content_type="application/json", HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["step"], 0)

    def test_shared_api_success_is_bound_to_browser_and_records_once(self):
        row = self.schedule()
        self.enroll()
        self.client.get(reverse("workforce:point"))
        endpoint = reverse("workforce:point_api")
        with self.at(row.starts_at), patch("apps.workforce.views.readiness", return_value=("",True)):
            response = self.client.post(endpoint, data={"operation":"start", "action":"IN"}, content_type="application/json")
        challenge = FaceChallenge.objects.get(pk=response.json()["id"])
        sign = -1 if challenge.poses[1] == "LEFT" else 1
        for index, yaw in enumerate((.2, .2+sign*.14, .2)):
            with self.at(row.starts_at+timedelta(seconds=3+3*index)), patch("apps.workforce.face.extract_frame", return_value={"hash":str(index),"vector":vector(),"yaw":yaw}):
                response = self.client.post(endpoint, data={"operation":"frame","id":str(challenge.pk),"frame":"jpeg"}, content_type="application/json")
            self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["recorded"])
        self.assertEqual(Attendance.objects.count(), 1)
        with self.at(row.starts_at+timedelta(seconds=15)):
            replay = self.client.post(endpoint, data={"operation":"frame","id":str(challenge.pk),"frame":"jpeg"}, content_type="application/json")
        self.assertEqual(replay.status_code, 400)
        self.assertEqual(Attendance.objects.count(), 1)

    def test_pose_progress_is_relative_and_does_not_accept_no_turn(self):
        self.assertTrue(pose_matches(.23, "CENTER"))
        self.assertTrue(pose_matches(.09, "LEFT", .23))
        self.assertFalse(pose_matches(.23, "LEFT", .23))
        self.assertFalse(pose_matches(.42, "CENTER", .23))
        self.assertAlmostEqual(pose_feedback(.17, "LEFT", .23)["movement"], .5)
