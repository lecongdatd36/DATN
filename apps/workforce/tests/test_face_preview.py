from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.workforce.models import Attendance, AttendanceLog, FaceChallenge, FaceProfile
from .test_workforce import WorkforceFixture, vector


class FacePreviewTests(WorkforceFixture):
    def setUp(self):
        self.client.force_login(self.manager)
        self.endpoint = reverse('workforce:face_test_api')
        self.ready = patch('apps.workforce.views.readiness', return_value=('', True))
        self.ready.start()
        self.addCleanup(self.ready.stop)

    def preview(self, sample=None):
        with patch('apps.workforce.face.extract_frame', return_value={
            'vector': sample or vector(), 'yaw': 0, 'hash': 'not-persisted',
        }):
            return self.client.post(self.endpoint, {'frame': 'test-only'}, content_type='application/json')

    def enroll(self, employee=None, sample=None):
        return FaceProfile.objects.create(employee=employee or self.employee,
            embeddings=[sample or vector()], consent_at=timezone.now())

    def assert_no_attendance(self):
        self.assertFalse(Attendance.objects.exists())
        self.assertFalse(AttendanceLog.objects.exists())
        self.assertFalse(FaceChallenge.objects.exists())

    def test_preview_is_separate_from_enrollment_and_attendance(self):
        response = self.client.get(reverse('workforce:face_test'))
        self.assertContains(response, 'data-face-test')
        self.assertContains(response, 'data-camera-placeholder')
        self.assertContains(response, 'Chưa bắt đầu kiểm thử')
        self.assertContains(response, reverse('workforce:point'))
        self.assertContains(self.client.get(reverse('workforce:faces')), reverse('workforce:face_test'))
        self.assertIn('no-store', response['Cache-Control'])
        self.assert_no_attendance()

    def test_matched_preview_repeated_never_records_attendance_or_changes_profile(self):
        profile = self.enroll()
        updated = profile.updated_at
        for attempt in range(2):
            response = self.preview()
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertTrue(data['identified'])
            self.assertFalse(data['recorded'])
            self.assertEqual(data['name'], self.employee.full_name)
            self.assertEqual(data['employee_code'], self.employee.employee_code)
            self.assertEqual(data['similarity'], 1)
            self.assertNotIn('vector', data)
            self.assertNotIn('hash', data)
            self.assertIn('no-store', response['Cache-Control'])
        profile.refresh_from_db()
        self.assertEqual(profile.updated_at, updated)
        self.assertEqual(profile.embeddings, [vector()])
        self.assert_no_attendance()

    def test_unknown_and_ambiguous_faces_do_not_expose_a_person(self):
        self.enroll()
        data = self.preview(vector(1)).json()
        self.assertEqual(data['code'], 'no_match')
        self.assertFalse(data['identified'])
        self.assertNotIn('name', data)
        self.enroll(self.other)
        data = self.preview().json()
        self.assertEqual(data['code'], 'no_match')
        self.assertNotIn('name', data)
        self.assert_no_attendance()

    def test_missing_or_inactive_profile_explains_without_identity(self):
        self.assertEqual(self.preview().json()['code'], 'no_profiles')
        self.enroll()
        self.employee.user.is_active = False
        self.employee.user.save(update_fields=['is_active'])
        data = self.preview().json()
        self.assertEqual(data['code'], 'no_profiles')
        self.assertNotIn('name', data)
        self.assert_no_attendance()

    def test_invalid_frame_and_unavailable_engine_show_real_reason(self):
        with patch('apps.workforce.face.extract_frame', side_effect=ValidationError('Ảnh mờ.')):
            response = self.client.post(self.endpoint, {'frame': 'bad'}, content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['message'], 'Ảnh mờ.')
        with patch('apps.workforce.views.readiness', return_value=('Chưa có mô hình.', False)):
            response = self.preview()
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json()['message'], 'Chưa có mô hình.')
            self.assertContains(self.client.get(reverse('workforce:face_test')), 'Chưa có mô hình.')
        self.assert_no_attendance()

    def test_manager_permission_post_and_csrf_are_required(self):
        self.assertEqual(self.client.get(self.endpoint).status_code, 405)
        protected = Client(enforce_csrf_checks=True)
        protected.force_login(self.manager)
        self.assertEqual(protected.post(self.endpoint, {'frame': 'bad'}, content_type='application/json').status_code, 403)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse('workforce:face_test')).status_code, 403)
        self.assertEqual(self.preview().status_code, 403)
        self.client.logout()
        self.assertEqual(self.preview().status_code, 302)
        self.assert_no_attendance()
