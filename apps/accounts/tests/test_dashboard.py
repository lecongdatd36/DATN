from datetime import datetime, time, timedelta
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from apps.orders.models import Order, Invoice
from apps.accounts.dashboard import dashboard_data


class ManagementDashboardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager=get_user_model().objects.create_superuser(username='dashboard_manager',password='test-password')
        cls.staff=get_user_model().objects.create_user(username='dashboard_staff')
        cls.start=timezone.make_aware(datetime.combine(timezone.localdate(),time.min))
        cls.order=Order.objects.create(order_code='DASH001',total_amount=125000)
        cls.paid=Invoice.objects.create(order=cls.order,invoice_code='DASH001',status='PAID',total=125000,closed_at=cls.start+timedelta(minutes=1))
        other=Order.objects.create(order_code='DASH002')
        Invoice.objects.create(order=other,invoice_code='DASH002',status='UNPAID',total=999000)
        old=Order.objects.create(order_code='DASH003')
        Invoice.objects.create(order=old,invoice_code='DASH003',status='PAID',total=50000,closed_at=cls.start-timedelta(seconds=1))

    def test_revenue_uses_paid_closed_time_and_zero_fills_chart(self):
        data=dashboard_data(self.manager,7)
        self.assertEqual(data['revenue'],125000)
        self.assertEqual(data['chart']['revenue'][-1],125000)
        self.assertEqual(data['chart']['revenue'][-2],50000)
        self.assertEqual(len(data['chart']['labels']),7)
        self.assertEqual(data['chart']['revenue'][0],0)
        self.assertEqual(sum(row['count'] for row in data['distribution']),data['order_count'])

    def test_manager_page_renders_chart_and_populated_order_without_writes(self):
        self.client.force_login(self.manager)
        response=self.client.get(reverse('accounts:workspace'),{'days':'30'})
        self.assertContains(response,'dashboard-chart-data')
        self.assertContains(response,'DASH001')
        self.assertEqual(response.context['dashboard']['days'],30)
        self.assertEqual(Order.objects.count(),3)
        self.assertEqual(Invoice.objects.count(),3)
        self.assertIn('no-store',response['Cache-Control'])
        response=self.client.get(reverse('accounts:workspace'),{'days':'bad'})
        self.assertEqual(response.context['dashboard']['days'],7)

    def test_unprivileged_staff_keeps_workspace_without_financial_data(self):
        self.client.force_login(self.staff)
        response=self.client.get(reverse('accounts:workspace'))
        self.assertNotContains(response,'dashboard-chart-data')
        self.assertNotContains(response,'DASH001')
        self.assertNotIn('dashboard',response.context)

    def test_report_only_user_cannot_read_customer_orders_or_inventory(self):
        self.staff.user_permissions.add(Permission.objects.get(content_type__app_label='reports',codename='view_report'))
        self.client.force_login(self.staff)
        response=self.client.get(reverse('accounts:workspace'))
        self.assertEqual(response.status_code,200)
        data=response.context['dashboard']
        self.assertEqual(data['recent_orders'],[])
        self.assertEqual(data['distribution'],[])
        self.assertNotIn('low_stock',data)
        self.assertNotIn('upcoming_bookings',data)
        self.assertNotContains(response,'DASH001')
