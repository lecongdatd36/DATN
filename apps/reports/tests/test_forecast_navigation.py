from datetime import date
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

SNAPSHOT={'ready':True,'is_demo':True,'is_stale':False,'data_source':'mo_phong',
    'date_from':date(2026,11,11),'date_to':date(2026,11,17),'trained_until':date(2026,11,10),
    'rows':[{'day':date(2026,11,11+i),'orders':20+i} for i in range(7)],
    'mae':5.45,'baseline_mae':7.71}

class ForecastNavigationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager=get_user_model().objects.create_superuser(username='forecast_nav_manager',password='test')
        cls.staff=get_user_model().objects.create_user(username='forecast_nav_staff')

    def test_manager_has_visible_links_and_read_only_dedicated_forecast(self):
        self.client.force_login(self.manager)
        with patch('apps.reports.forecast.get_order_forecast',return_value=SNAPSHOT):
            home=self.client.get(reverse('accounts:workspace'))
        self.assertContains(home,'cqd-operation-tools')
        self.assertContains(home,reverse('bookings:availability'))
        self.assertContains(home,reverse('reports:order_forecast'))
        with patch('apps.reports.views.get_order_forecast',return_value=SNAPSHOT) as loader:
            response=self.client.get(reverse('reports:order_forecast'))
        loader.assert_called_once_with()
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.context['forecast_total'],161)
        self.assertEqual(len(response.context['forecast_chart']),7)
        self.assertContains(response,'Nhịp phục vụ sắp tới')
        self.assertContains(response,'Dữ liệu mô phỏng')
        self.assertIn('no-store',response['Cache-Control'])

    def test_new_forecast_link_does_not_grant_report_permission(self):
        self.client.force_login(self.staff)
        home=self.client.get(reverse('accounts:workspace'))
        self.assertNotContains(home,reverse('reports:order_forecast'))
        self.assertEqual(self.client.get(reverse('reports:order_forecast')).status_code,403)
        self.staff.user_permissions.add(Permission.objects.get(content_type__app_label='bookings',codename='view_booking'))
        self.client.force_login(self.staff)
        home=self.client.get(reverse('accounts:workspace'))
        self.assertContains(home,'Gợi ý bàn phù hợp')
        self.assertNotContains(home,reverse('reports:order_forecast'))

    def test_missing_forecast_shows_message_without_fake_chart(self):
        self.client.force_login(self.manager)
        with patch('apps.reports.views.get_order_forecast',return_value={'ready':False,'is_demo':True}):
            response=self.client.get(reverse('reports:order_forecast'))
        self.assertContains(response,'Chưa có kết quả dự báo hợp lệ')
        self.assertNotContains(response,'class="forecast-bars"')
