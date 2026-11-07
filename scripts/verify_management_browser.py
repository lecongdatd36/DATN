"""Verify management layouts in Chrome against an isolated, disposable database."""
import json
import mimetypes
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from datetime import timedelta
from uuid import uuid4

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "QLNH.test_settings")
import django
django.setup()

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.wsgi import get_wsgi_application
from django.db import connection, connections
from django.test import override_settings
from django.test.runner import DiscoverRunner
from django.urls import reverse
from django.utils import timezone
from apps.bookings.models import Booking
from apps.customers.models import Customer
from apps.inventory.models import Ingredient, InventoryTransaction
from apps.menu.models import Category, Dish, Unit
from apps.orders import services
from apps.seating.models import Area, DiningTable
from scripts.verify_staff_mobile_browser import QuietHandler, ThreadedServer, make_server


def main():
    connection.settings_dict["TEST"]["NAME"] = "test_qlnh_management_" + uuid4().hex
    runner = DiscoverRunner(verbosity=0, interactive=False)
    old_config = runner.setup_databases()
    server = None
    try:
        connection.settings_dict["CONN_MAX_AGE"] = 0
        for role in ("MANAGER", "WAITER", "CASHIER", "INVENTORY", "KITCHEN"):
            user = get_user_model().objects.create_user(username="browser-" + role.lower(), password="Browser-test-only-123")
            user.groups.add(Group.objects.get(name=role))
        area = Area.objects.create(name="Khu vực kiểm tra")
        table = DiningTable.objects.create(code="B01", area=area, capacity=4)
        reserved = DiningTable.objects.create(code="B02", area=area, capacity=4, status="RESERVED")
        DiningTable.objects.create(code="B03", area=area, capacity=4, status="CLEANING")
        DiningTable.objects.create(code="B04", area=area, capacity=4)
        customer = Customer.objects.create(full_name="Khách kiểm tra mobile", phone="0901234567")
        dish = Dish.objects.create(code="UI01", name="Cơm gà", price=50000,
                                   category=Category.objects.create(name="Món chính"), unit=Unit.objects.create(name="Phần"))
        waiter = get_user_model().objects.get(username="browser-waiter")
        kitchen = get_user_model().objects.get(username="browser-kitchen")
        order = services.open_table(actor=waiter, table_id=table.pk, guest_count=2, customer_id=customer.pk, note="Ưu tiên phục vụ cùng lúc")
        items = []
        for note in ("Ít cay", "Không hành", "Mang ra cùng món chính"):
            order.refresh_from_db()
            items.append(services.add_item(actor=waiter, order_id=order.pk, expected_revision=order.revision,
                                            dish_id=dish.pk, quantity=1, note=note))
        order.refresh_from_db()
        services.send_to_kitchen(actor=waiter, order_id=order.pk, expected_revision=order.revision)
        for item, statuses in ((items[1], ("COOKING",)), (items[2], ("COOKING", "READY"))):
            for status in statuses:
                order.refresh_from_db()
                services.transition_item(actor=kitchen, order_id=order.pk, item_id=item.pk,
                                         expected_revision=order.revision, target=status)
        now = timezone.now()
        Booking.objects.create(customer=customer, customer_name=customer.full_name, customer_phone=customer.phone,
                               table=reserved, party_size=2, starts_at=now-timedelta(minutes=2),
                               ends_at=now+timedelta(hours=1), status="CONFIRMED")
        rice = Ingredient.objects.create(code="RICE", name="Gạo thơm", unit="kg", stock_quantity=50)
        for kind, quantity in (("SALE_USAGE", 7), ("EXPORT", 2), ("SALE_RETURN", 1), ("WASTE", 0.5)):
            InventoryTransaction.objects.create(ingredient=rice, transaction_type=kind, quantity=quantity,
                                                stock_before=50, stock_after=40, note="Giao dịch kiểm tra giao diện")
        application = get_wsgi_application()
        routes = {name: reverse(name) for name in (
            "accounts:workspace", "accounts:login", "inventory:daily_usage", "inventory:workspace",
            "bookings:create", "bookings:settings", "bookings:list", "seating:table_list", "menu:dish_list",
            "customers:customer_list", "accounts:account_list", "employees:employee_list", "reports:dashboard",
            "sales:workspace", "sales:mobile", "kitchen:workspace",
        )}
        routes.update({
            "mobile:tables": reverse("sales:mobile"),
            "mobile:menu": reverse("sales:mobile") + f"?page=menu&order={order.pk}",
            "mobile:order": reverse("sales:mobile") + f"?page=order&order={order.pk}",
            "mobile:checkout": reverse("sales:mobile") + f"?page=checkout&order={order.pk}",
            "mobile:tasks": reverse("sales:mobile") + "?page=tasks",
            "mobile:personal": reverse("sales:mobile") + "?page=personal",
        })

        def wsgi(environ, start_response):
            path = environ.get("PATH_INFO", "")
            if path == "/__management_test__/routes":
                body = json.dumps(routes).encode()
                start_response("200 OK", [("Content-Type", "application/json"), ("Content-Length", str(len(body)))])
                return [body]
            if path.startswith("/static/"):
                root = (BASE / "static").resolve()
                target = (root / path.removeprefix("/static/")).resolve()
                if target.is_relative_to(root) and target.is_file():
                    body = target.read_bytes()
                    start_response("200 OK", [("Content-Type", mimetypes.guess_type(target)[0] or "application/octet-stream"), ("Content-Length", str(len(body)))])
                    return [body]
            return application(environ, start_response)

        server = make_server("127.0.0.1", 0, wsgi, server_class=ThreadedServer, handler_class=QuietHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        output = BASE / "artifacts/staff-mobile/management"
        output.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="qlnh-management-", ignore_cleanup_errors=True) as profile:
            result = subprocess.run(["node", str(BASE / "scripts/run_management_chrome.cjs"),
                                     f"http://127.0.0.1:{server.server_port}", profile, str(output)],
                                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=160,
                                    env={k: v for k, v in os.environ.items() if k.upper() in {
                                        "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATH", "USERPROFILE", "LOCALAPPDATA", "APPDATA", "COMSPEC"}})
            print(result.stdout or result.stderr)
            if result.returncode:
                raise RuntimeError("Management browser verification failed")
    finally:
        if server:
            server.shutdown()
            server.server_close()
        connections.close_all()
        runner.teardown_databases(old_config)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    with override_settings(DEBUG=True, ALLOWED_HOSTS=["127.0.0.1", "localhost", "testserver"],
                           SECURE_SSL_REDIRECT=False, SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False,
                           PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"]):
        main()
