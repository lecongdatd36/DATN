from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase, override_settings

from ai_tools.forecast_update import update_forecast
from ai_tools.tests.test_forecast_update import PROJECT, fixture_trainer
from apps.reports.forecast import get_order_forecast
from apps.reports.views import ReportDashboardView


class ForecastDashboardTests(SimpleTestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.reference = date(2026, 12, 12)
        self.settings_override = override_settings(ORDER_FORECAST_ROOT=self.root, ORDER_FORECAST_SOURCE="mo_phong")
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)

    def update(self, reference=None):
        return update_forecast(PROJECT, self.root, reference_date=reference or self.reference,
                               trainer=fixture_trainer)

    def test_dashboard_context_reads_new_publication_without_training(self):
        first = self.update()
        def context():
            view = ReportDashboardView()
            request = RequestFactory().get("/bao-cao/")
            request.user = AnonymousUser()
            view.setup(request)
            with patch("apps.reports.views.report_data", return_value={}), patch("subprocess.run", side_effect=AssertionError("No training in requests")):
                return view.get_context_data()
        self.assertEqual(context()["order_forecast"]["run_id"], first["run_id"])
        second = self.update(self.reference + timedelta(days=1))
        current = context()
        self.assertEqual(current["order_forecast"]["run_id"], second["run_id"])
        self.assertEqual(current["order_forecast"]["date_from"], date(2026, 12, 13))
        self.assertIn("filter_form", current)
        self.assertTrue(current["report_ready"])

    def test_stale_and_failed_update_are_visible(self):
        self.update()
        def fail(*args): raise RuntimeError("training failed")
        with self.assertLogs("qlnh.forecast_update", level="ERROR"), self.assertRaises(RuntimeError):
            update_forecast(PROJECT, self.root, reference_date=self.reference + timedelta(days=1), trainer=fail)
        result = get_order_forecast(self.reference + timedelta(days=1))
        self.assertTrue(result["ready"])
        self.assertTrue(result["is_stale"])
        self.assertTrue(result["last_update_failed"])
        html = render_to_string("reports/includes/order_forecast.html", {"order_forecast": result})
        self.assertIn("chưa được cập nhật cho hôm nay", html)
        self.assertIn("Lần cập nhật gần nhất thất bại", html)
        self.assertIn("Dữ liệu mô phỏng", html)
        self.update(self.reference + timedelta(days=1))
        result = get_order_forecast(self.reference + timedelta(days=1))
        self.assertFalse(result["is_stale"])
        self.assertFalse(result["last_update_failed"])

    def test_corrupt_result_does_not_break_dashboard(self):
        manifest = self.update()
        path = self.root / "mo_phong/runs" / manifest["run_id"] / "evaluation.json"
        path.write_text("broken")
        with self.assertLogs("apps.reports.forecast", level="ERROR"):
            result = get_order_forecast(self.reference)
        self.assertFalse(result["ready"])
        html = render_to_string("reports/includes/order_forecast.html", {"order_forecast": result})
        self.assertIn("Chưa có kết quả dự báo hợp lệ", html)

    def test_source_configuration_has_no_demo_fallback(self):
        self.update()
        with override_settings(ORDER_FORECAST_SOURCE="application_export"):
            with self.assertLogs("apps.reports.forecast", level="ERROR"):
                result = get_order_forecast(self.reference)
            self.assertFalse(result["ready"])
            self.assertFalse(result["is_demo"])
            html = render_to_string("reports/includes/order_forecast.html", {"order_forecast": result})
            self.assertIn("Dữ liệu ứng dụng", html)
            self.assertNotIn("Dữ liệu mô phỏng", html)

    def test_report_permissions_still_enforced(self):
        request = RequestFactory().get("/bao-cao/")
        request.user = AnonymousUser()
        self.assertEqual(ReportDashboardView.as_view()(request).status_code, 302)
        from apps.accounts.models import User
        request.user = User(username="no-report-permission", is_active=True)
        with patch.object(User, "has_perm", return_value=False), self.assertRaises(PermissionDenied):
            ReportDashboardView.as_view()(request)

    def test_invalid_revenue_filter_keeps_form_and_forecast(self):
        self.update()
        view = ReportDashboardView()
        view.setup(RequestFactory().get("/bao-cao/", {"date_from": "invalid", "date_to": "2026-12-12"}))
        with patch("apps.reports.views.report_data", side_effect=AssertionError("Invalid dates must not query reports")):
            context = view.get_context_data()
        self.assertTrue(context["filter_form"].errors)
        self.assertTrue(context["order_forecast"]["ready"])
