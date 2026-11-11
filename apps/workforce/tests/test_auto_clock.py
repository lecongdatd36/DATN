from datetime import timedelta
from unittest.mock import patch
from django.utils import timezone
from django.urls import reverse
from apps.workforce import services
from apps.workforce.models import Attendance, FaceProfile
from .test_workforce import WorkforceFixture, vector


class AutomaticClockTests(WorkforceFixture):
    def enroll(self):
        FaceProfile.objects.create(employee=self.employee, embeddings=[vector()], consent_at=timezone.now())

    def frame(self, challenge, moment, yaw=0):
        with self.at(moment), patch('apps.workforce.face.extract_frame', return_value={
            'vector':vector(),'yaw':yaw,'hash':str(moment)}):
            return services.process_frame(raw_token='a'*64,challenge_id=challenge.pk,frame='test')

    def complete(self, moment):
        with self.at(moment):
            challenge=services.begin_challenge(raw_token='a'*64,action='AUTO')
        for index,yaw in enumerate((0,-.2 if challenge.poses[1]=='LEFT' else .2,0)):
            result=self.frame(challenge,moment+timedelta(seconds=3*(index+1)),yaw)
        return result

    def test_one_action_automatically_records_in_then_out_from_ledger(self):
        row=self.schedule();self.enroll()
        first=self.complete(row.starts_at)
        self.assertTrue(first['recorded']);self.assertEqual(first['action'],'IN')
        self.assertEqual(first['employee_code'],self.employee.employee_code)
        self.assertEqual(first['similarity'],1)
        self.assertIn('recorded_at',first)
        second=self.complete(row.ends_at)
        self.assertTrue(second['recorded']);self.assertEqual(second['action'],'OUT')
        self.assertEqual(Attendance.objects.count(),1)
        self.assertIsNotNone(Attendance.objects.get().checked_out_at)

    def test_rapid_repeat_never_turns_a_new_clock_in_into_clock_out(self):
        row=self.schedule();self.enroll();self.complete(row.starts_at)
        with self.at(row.starts_at+timedelta(seconds=15)):
            challenge=services.begin_challenge(raw_token='a'*64,action='AUTO')
        result=self.frame(challenge,row.starts_at+timedelta(seconds=18))
        self.assertTrue(result['done']);self.assertFalse(result['recorded'])
        self.assertEqual(result['code'],'recent_clock')
        self.assertIsNone(Attendance.objects.get().checked_out_at)

    def test_second_pending_session_cannot_flip_action_after_another_records(self):
        row=self.schedule();self.enroll()
        with self.at(row.starts_at):
            pending=services.begin_challenge(raw_token='a'*64,action='AUTO')
        self.frame(pending,row.starts_at+timedelta(seconds=3))
        # A different station records first while this station is mid-challenge.
        Attendance.objects.create(schedule=row,checked_in_at=row.starts_at+timedelta(seconds=4))
        result=self.frame(pending,row.starts_at+timedelta(seconds=6),.2)
        self.assertTrue(result['done']);self.assertFalse(result['recorded'])
        self.assertEqual(result['code'],'recent_clock')
        self.assertIsNone(Attendance.objects.get().checked_out_at)

    def test_missing_schedule_explained_without_writing_attendance(self):
        self.enroll()
        now=timezone.now()
        with self.at(now):challenge=services.begin_challenge(raw_token='a'*64,action='AUTO')
        result=self.frame(challenge,now+timedelta(seconds=3))
        self.assertEqual(result['code'],'no_schedule')
        self.assertTrue(result['done']);self.assertFalse(result['recorded'])
        self.assertFalse(Attendance.objects.exists())

    def test_point_has_one_clock_button_and_no_gps_controls(self):
        response=self.client.get(reverse('workforce:point'))
        self.assertContains(response,'data-clock-action="AUTO"',count=1)
        self.assertNotContains(response,'data-clock-action="IN"')
        self.assertNotContains(response,'data-clock-action="OUT"')
        self.assertNotContains(response,'data-get-location')
        self.assertContains(response,'data-result-card')
        self.assertFalse(Attendance.objects.exists())
