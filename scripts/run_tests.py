"""Chạy test trên database PostgreSQL mới, tên riêng cho mỗi lần chạy."""
import os
from pathlib import Path
import sys
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "QLNH.settings")

import django

django.setup()

from django.db import connection
from django.test.runner import DiscoverRunner

connection.settings_dict["TEST"]["NAME"] = f"test_qlnh_{uuid4().hex}"
runner = DiscoverRunner(verbosity=1, interactive=False)
raise SystemExit(bool(runner.run_tests(sys.argv[1:] or ["apps.accounts", "apps.employees", "apps.customers", "apps.seating", "apps.bookings", "apps.menu"])))
