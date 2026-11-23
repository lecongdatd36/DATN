"""Capture real application pages using an isolated PostgreSQL test database."""
from datetime import timedelta
from decimal import Decimal
import json
import logging
import mimetypes
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "QLNH.test_settings")
import django
django.setup()
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.wsgi import get_wsgi_application
from django.db import connection, connections
from django.test import Client, override_settings
from django.test.runner import DiscoverRunner
from django.urls import reverse
from django.utils import timezone
from apps.bookings import services as booking_services
from apps.customers.models import Customer
from apps.employees.models import EmployeeProfile, JobPosition
from apps.inventory import services as inventory_services
from apps.inventory.models import Ingredient, Supplier, RecipeIngredient
from apps.menu.models import Category, Dish, Unit
from apps.orders import services as order_services
from apps.orders.models import Invoice
from apps.seating.models import Area, DiningTable
from scripts.verify_staff_mobile_browser import QuietHandler, ThreadedServer, make_server

OUT = ROOT / "docs" / "section-3-3"
SHOTS = OUT / "screenshots"
SHOTS.mkdir(parents=True, exist_ok=True)
NODE = r"C:\Users\Admin\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"


def main():
    logging.getLogger("django.request").setLevel(logging.CRITICAL)
    connection.settings_dict["TEST"]["NAME"] = "test_qlnh_section33_" + uuid4().hex
    runner = DiscoverRunner(verbosity=0, interactive=False)
    previous = runner.setup_databases()
    server = None
    try:
        connection.settings_dict["CONN_MAX_AGE"] = 0
        User = get_user_model()
        root = User.objects.create_superuser(username="quantri-minhhoa", password="Section33-fixture-only-123")
        users = {}
        for role, label in [("MANAGER", "quanly"), ("WAITER", "phucvu"), ("KITCHEN", "bep"), ("CASHIER", "thungan"), ("INVENTORY", "thukho")]:
            user = User.objects.create_user(username="minhhoa-"+label, password="Section33-fixture-only-123")
            user.groups.add(Group.objects.get(name=role))
            users[role] = user
        employee = EmployeeProfile.objects.create(user=users["WAITER"], employee_code="NV0001", full_name="Nhân viên minh họa", phone="0900000001", job_position=JobPosition.objects.get(code="WAITER"), join_date=timezone.localdate())
        area = Area.objects.create(name="Tầng 1")
        tables = {i: DiningTable.objects.create(code=f"B{i:02}", area=area, capacity=seats) for i,seats in [(1,2),(2,4),(3,6),(4,4)]}
        tables[4].status = "CLEANING"
        tables[4].save(update_fields=("status",))
        customer = Customer.objects.create(full_name="Khách hàng minh họa", phone="0900000002")
        start = timezone.localtime(timezone.now()+timedelta(days=1)).replace(hour=18,minute=0,second=0,microsecond=0)
        booking = booking_services.save_booking(actor=root, customer_phone=customer.phone, table_id=tables[2].pk, party_size=4, starts_at=start, duration_minutes=120)
        booking = booking_services.transition_booking(actor=root, booking_id=booking.pk, target="CONFIRMED", expected_status=booking.status, expected_revision=booking.revision)
        category = Category.objects.create(name="Món chính")
        unit = Unit.objects.create(name="Phần")
        dish = Dish.objects.create(code="M001", name="Cơm gà", category=category, unit=unit, price=Decimal("65000"), tracks_inventory=True)
        Dish.objects.create(code="M002", name="Cơm chiên", category=category, unit=unit, price=Decimal("55000"))
        Dish.objects.create(code="M003", name="Cá kho", category=category, unit=unit, price=Decimal("75000"),status="SOLD_OUT")
        supplier = Supplier.objects.create(name="Nhà cung cấp minh họa", phone="0900000003", address="Địa chỉ dữ liệu kiểm thử")
        rice = Ingredient.objects.create(code="GAO", name="Gạo thơm", unit="kg", stock_quantity=0, low_stock_threshold=5)
        receipt = inventory_services.create_purchase_receipt(actor=root, supplier_id=supplier.pk, invoice_number="NCC-MH-001", note="Dữ liệu minh họa báo cáo")
        inventory_services.add_purchase_line(actor=root,receipt_id=receipt.pk,ingredient_id=rice.pk,quantity=Decimal("50"),unit_cost=Decimal("20000"))
        inventory_services.confirm_purchase_receipt(actor=root,receipt_id=receipt.pk)
        RecipeIngredient.objects.create(dish=dish,ingredient=rice,quantity=Decimal("0.200"))

        def serving_order(table, paid=False):
            order=order_services.open_table(actor=root,table_id=table.pk,guest_count=2,customer_id=customer.pk)
            item=order_services.add_item(actor=root,order_id=order.pk,expected_revision=order.revision,dish_id=dish.pk,quantity=2,note="Ít cay")
            order.refresh_from_db()
            order_services.send_to_kitchen(actor=root,order_id=order.pk,expected_revision=order.revision)
            if paid:
                for status in ("COOKING","READY","SERVED"):
                    order.refresh_from_db()
                    order_services.transition_item(actor=root,order_id=order.pk,item_id=item.pk,expected_revision=order.revision,target=status)
                order.refresh_from_db()
                order_services.request_payment(actor=root,order_id=order.pk,expected_revision=order.revision)
                order_services.process_payment(actor=root,order_id=order.pk,payment_method="BANK_TRANSFER",transaction_code="MH-THU-001")
            return order
        live_order=serving_order(tables[3])
        paid_order=serving_order(tables[1],True)
        rice.refresh_from_db()
        assert rice.stock_quantity == Decimal("49.200")
        assert Invoice.objects.get(order=paid_order).status == "PAID"

        sessions={}
        for key,user in {**users,"ROOT":root}.items():
            client=Client()
            client.force_login(user)
            sessions[key]=client.cookies[settings.SESSION_COOKIE_NAME].value
        routes={name:reverse(name) for name in ["accounts:login","accounts:workspace","kitchen:workspace","employees:employee_list","seating:table_list","bookings:list","menu:dish_list","inventory:workspace","reports:dashboard","orders:invoice_list","sales:mobile"]}
        routes.update(employee_edit=reverse("employees:employee_update",args=[employee.pk]),booking_detail=reverse("bookings:detail",args=[booking.pk]),order_detail=reverse("orders:detail",args=[live_order.pk]),invoice_order=reverse("orders:detail",args=[paid_order.pk]),receipt_detail=reverse("inventory:purchase_detail",args=[receipt.pk]))
        checks=[]
        for role in users:
            client=Client();client.force_login(users[role])
            for name in ["employees:employee_list","reports:dashboard","inventory:workspace","menu:dish_list"]:
                response=client.get(routes[name])
                checks.append({"role":role,"route":name,"status":response.status_code})
        config={"routes":routes,"sessions":sessions,"cookie":settings.SESSION_COOKIE_NAME}
        application=get_wsgi_application()
        def wsgi(environ,start_response):
            request_path=environ.get("PATH_INFO","")
            if request_path=="/__section33__/config":
                body=json.dumps(config).encode()
                start_response("200 OK",[("Content-Type","application/json"),("Cache-Control","no-store")])
                return [body]
            if request_path.startswith("/static/"):
                static_root=(ROOT/"static").resolve()
                target=(static_root/request_path.removeprefix("/static/")).resolve()
                if target.is_relative_to(static_root) and target.is_file():
                    body=target.read_bytes()
                    start_response("200 OK",[("Content-Type",mimetypes.guess_type(target)[0] or "application/octet-stream")])
                    return [body]
            return application(environ,start_response)
        server=make_server("127.0.0.1",0,wsgi,server_class=ThreadedServer,handler_class=QuietHandler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        with tempfile.TemporaryDirectory(prefix="qlnh-section33-",ignore_cleanup_errors=True) as profile:
            result=subprocess.run([NODE,str(ROOT/"scripts/capture_section_3_3.cjs"),f"http://127.0.0.1:{server.server_port}",profile,str(SHOTS)],capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=140)
            print(result.stdout)
            if result.returncode: raise RuntimeError(result.stderr)
        employee.refresh_from_db()
        assert employee.full_name == "Nhân viên phục vụ minh họa"
        evidence={"scope":"Real application UI on a disposable test database; all names and transactions are synthetic fixtures.","captured_at":timezone.localtime().isoformat(),"permission_checks":checks,"booking_status":booking.status,"inventory_received":"50.000 kg","inventory_consumed":"0.800 kg","inventory_balance":str(rice.stock_quantity),"paid_invoice_total":str(Invoice.objects.get(order=paid_order).total),"employee_update_persisted":True}
        (OUT/"ui-evidence.json").write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding="utf-8")
        print("Verified booking, inventory, employee update and paid invoice on isolated fixtures.")
    finally:
        if server: server.shutdown();server.server_close()
        connections.close_all()
        runner.teardown_databases(previous)


if __name__=="__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    with override_settings(DEBUG=True,ALLOWED_HOSTS=["127.0.0.1","localhost","testserver"],SECURE_SSL_REDIRECT=False,SESSION_COOKIE_SECURE=False,CSRF_COOKIE_SECURE=False,PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"]):
        main()
