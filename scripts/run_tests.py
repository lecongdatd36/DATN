"""Chạy test trên database UUID riêng; mặc định SQL Server ở nhánh này."""
import os
from pathlib import Path
import sys
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "QLNH.sqlserver_test_settings")

import django

django.setup()

from django.db import connection
from django.test.runner import DiscoverRunner

connection.settings_dict["TEST"]["NAME"] = f"test_qlnh_{uuid4().hex}"
runner = DiscoverRunner(verbosity=1, interactive=False)
raise SystemExit(bool(runner.run_tests(sys.argv[1:] or ["apps.accounts", "apps.employees", "apps.workforce", "apps.reservations", "apps.customers", "apps.seating", "apps.bookings", "apps.menu", "apps.orders", "apps.inventory", "apps.reports", "apps.customer_portal.tests", "ai_tools.tests.test_inference", "ai_tools.tests.test_forecast_update", "ai_tools.tests.test_quality"])))
