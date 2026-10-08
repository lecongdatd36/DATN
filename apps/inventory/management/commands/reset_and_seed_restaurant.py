from datetime import timedelta
from decimal import Decimal

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone

from apps.bookings.models import Booking, BookingSettings
from apps.customers.models import Customer, MembershipTier
from apps.employees.models import EmployeeProfile, JobPosition
from apps.inventory.models import Ingredient, PurchaseReceipt, RecipeIngredient, Stocktake, Supplier, WasteRecord
from apps.inventory.services import (
    add_purchase_line, confirm_purchase_receipt, create_purchase_receipt, create_stocktake,
    post_stocktake, record_waste,
)
from apps.menu.models import Category, Dish, Unit
from apps.orders import services as order_services
from apps.orders.models import Invoice, Order, OrderItem, Payment, PromotionCode
from apps.seating.models import Area, DiningTable


class Command(BaseCommand):
    help = "Xóa dữ liệu nghiệp vụ, giữ tài khoản/quyền và tạo bộ dữ liệu nhà hàng hoàn chỉnh."

    def add_arguments(self, parser):
        parser.add_argument("--yes", action="store_true", help="Xác nhận xóa toàn bộ dữ liệu nghiệp vụ.")

    def handle(self, *args, **options):
        if not options["yes"]:
            raise CommandError("Thêm --yes để xác nhận xóa dữ liệu nghiệp vụ.")
        if connection.vendor != "postgresql":
            raise CommandError("Lệnh này chỉ hỗ trợ PostgreSQL.")
        with transaction.atomic():
            self._truncate_domain_tables()
            summary = self._seed()
        self.stdout.write(self.style.SUCCESS(f"Restaurant demo database created: {summary}"))

    def _truncate_domain_tables(self):
        User = get_user_model()
        preserved = {
            "django_migrations",
            ContentType._meta.db_table,
            Permission._meta.db_table,
            Group._meta.db_table,
            Group.permissions.through._meta.db_table,
            User._meta.db_table,
            User.groups.through._meta.db_table,
            User.user_permissions.through._meta.db_table,
        }
        tables = sorted(set(connection.introspection.table_names()) - preserved)
        if not tables:
            return
        quoted = ", ".join(connection.ops.quote_name(table) for table in tables)
        with connection.cursor() as cursor:
            cursor.execute(f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE")

    def _seed(self):
        now = timezone.now()
        today = timezone.localdate()
        User = get_user_model()
        actor = User.objects.filter(is_superuser=True, is_active=True).order_by("pk").first()
        if actor is None:
            raise CommandError("Không có tài khoản superuser đang hoạt động để tạo dữ liệu.")

        position_names = {
            "MANAGER": "Quản lý", "WAITER": "Nhân viên phục vụ", "KITCHEN": "Nhân viên bếp",
            "CASHIER": "Thu ngân", "INVENTORY": "Nhân viên kho",
        }
        positions = {}
        for code, name in position_names.items():
            group = Group.objects.get(name=code)
            positions[code] = JobPosition.objects.create(code=code, name=name, group=group, description=f"Vị trí {name.lower()}")
        for index, user in enumerate(User.objects.order_by("pk"), start=1):
            role = next((name for name in position_names if user.groups.filter(name=name).exists()), "MANAGER")
            EmployeeProfile.objects.create(
                user=user, employee_code=f"NV{index:03d}", full_name=user.get_full_name() or user.username,
                phone=f"090900{index:04d}", address="Thành phố Hồ Chí Minh",
                job_position=positions[role], join_date=today - timedelta(days=365 + index * 20),
            )

        areas = {
            name: Area.objects.create(name=name) for name in ("Tầng trệt", "Lầu 1", "Phòng VIP")
        }
        tables = {}
        for code, area, capacity, name in (
            ("T01", "Tầng trệt", 2, "Bàn cửa sổ"), ("T02", "Tầng trệt", 4, "Bàn trung tâm"),
            ("T03", "Tầng trệt", 4, "Bàn gần quầy"), ("T04", "Tầng trệt", 6, "Bàn gia đình"),
            ("L01", "Lầu 1", 4, "Bàn ban công"), ("L02", "Lầu 1", 4, "Bàn yên tĩnh"),
            ("L03", "Lầu 1", 6, "Bàn nhóm"), ("L04", "Lầu 1", 8, "Bàn tiệc nhỏ"),
            ("VIP01", "Phòng VIP", 8, "VIP Sen"), ("VIP02", "Phòng VIP", 10, "VIP Trúc"),
        ):
            tables[code] = DiningTable.objects.create(code=code, area=areas[area], capacity=capacity, name=name)

        tiers = {}
        for name, minimum, discount in (("Đồng", 0, 0), ("Bạc", 1_000_000, 3), ("Vàng", 3_000_000, 5), ("Kim cương", 8_000_000, 8)):
            tiers[name] = MembershipTier.objects.create(name=name, minimum_spending=minimum, discount_percent=discount)
        customer_rows = (
            ("Nguyễn Minh Anh", "0912000001"), ("Trần Quốc Bảo", "0912000002"),
            ("Lê Thu Hà", "0912000003"), ("Phạm Hoàng Nam", "0912000004"),
            ("Võ Ngọc Lan", "0912000005"), ("Đặng Gia Huy", "0912000006"),
            ("Bùi Thanh Mai", "0912000007"), ("Đỗ Đức Long", "0912000008"),
            ("Hoàng Khánh Linh", "0912000009"), ("Ngô Tuấn Kiệt", "0912000010"),
        )
        customers = [Customer.objects.create(full_name=name, phone=phone, membership_tier=tiers["Đồng"]) for name, phone in customer_rows]

        units = {name: Unit.objects.create(name=name) for name in ("Phần", "Tô", "Ly", "Chai", "Lon")}
        categories = {name: Category.objects.create(name=name) for name in ("Khai vị", "Món chính", "Món rau", "Đồ uống", "Tráng miệng")}
        dish_rows = (
            ("KV01", "Gỏi cuốn tôm thịt", "Khai vị", "Phần", 59000), ("KV02", "Chả giò hải sản", "Khai vị", "Phần", 69000),
            ("MC01", "Cơm sườn nướng", "Món chính", "Phần", 79000), ("MC02", "Cơm gà xối mỡ", "Món chính", "Phần", 75000),
            ("MC03", "Phở bò đặc biệt", "Món chính", "Tô", 89000), ("MC04", "Bún chả Hà Nội", "Món chính", "Phần", 85000),
            ("MC05", "Tôm rang me", "Món chính", "Phần", 129000), ("MC06", "Trứng chiên thịt", "Món chính", "Phần", 65000),
            ("RAU01", "Rau muống xào tỏi", "Món rau", "Phần", 49000), ("RAU02", "Rau củ luộc kho quẹt", "Món rau", "Phần", 59000),
            ("DU01", "Cà phê sữa đá", "Đồ uống", "Ly", 35000), ("DU02", "Trà chanh", "Đồ uống", "Ly", 32000),
            ("DU03", "Nước ngọt", "Đồ uống", "Chai", 25000), ("DU04", "Bia lon", "Đồ uống", "Lon", 30000),
            ("TM01", "Trái cây theo mùa", "Tráng miệng", "Phần", 49000), ("TM02", "Chè khúc bạch", "Tráng miệng", "Phần", 45000),
        )
        dishes = {
            code: Dish.objects.create(code=code, name=name, category=categories[category], unit=units[unit], price=price, tracks_inventory=True,
                                      description=f"{name} được chế biến theo công thức tiêu chuẩn của nhà hàng.")
            for code, name, category, unit, price in dish_rows
        }

        supplier_rows = (
            ("Thực phẩm An Phú", "0901000001", "12 Nguyễn Văn Linh"),
            ("Nông sản Xanh", "0901000002", "45 Quốc lộ 1A"),
            ("Đồ uống Sài Gòn", "0901000003", "88 Điện Biên Phủ"),
            ("Gia vị Việt", "0901000004", "18 Lê Văn Việt"),
        )
        suppliers = {name: Supplier.objects.create(name=name, phone=phone, address=address) for name, phone, address in supplier_rows}
        ingredient_rows = (
            ("NL-GAO", "Gạo thơm", "kg", 10), ("NL-BUN", "Bún/Phở tươi", "kg", 8),
            ("NL-THIT-HEO", "Thịt heo", "kg", 5), ("NL-THIT-BO", "Thịt bò", "kg", 4),
            ("NL-THIT-GA", "Thịt gà", "kg", 5), ("NL-TOM", "Tôm tươi", "kg", 3),
            ("NL-RAU", "Rau củ tổng hợp", "kg", 5), ("NL-TRUNG", "Trứng gà", "quả", 30),
            ("NL-DAU", "Dầu ăn", "lít", 3), ("NL-GIAVI", "Gia vị tổng hợp", "kg", 2),
            ("NL-HANHTOI", "Hành tỏi", "kg", 2), ("NL-CAPHE", "Cà phê", "kg", 1),
            ("NL-TRA", "Trà", "kg", 1), ("NL-SUA", "Sữa đặc", "lít", 2),
            ("NL-DUONG", "Đường", "kg", 3), ("NL-CHANH", "Chanh", "kg", 2),
            ("NL-NUOCNGOT", "Nước ngọt chai", "chai", 24), ("NL-BIA", "Bia lon", "lon", 24),
            ("NL-TRAI-CAY", "Trái cây", "kg", 4), ("NL-KHUC-BACH", "Khúc bạch", "kg", 2),
        )
        ingredients = {code: Ingredient.objects.create(code=code, name=name, unit=unit, low_stock_threshold=threshold)
                       for code, name, unit, threshold in ingredient_rows}

        receipt_specs = (
            ("PN20261001", "Thực phẩm An Phú", "HD-AP-1001", (("NL-THIT-HEO", 30, 105000), ("NL-THIT-BO", 20, 210000), ("NL-THIT-GA", 25, 85000), ("NL-TOM", 15, 180000), ("NL-TRUNG", 300, 3200))),
            ("PN20261002", "Nông sản Xanh", "HD-NSX-208", (("NL-GAO", 100, 23000), ("NL-BUN", 50, 18000), ("NL-RAU", 40, 32000), ("NL-HANHTOI", 10, 45000), ("NL-TRAI-CAY", 25, 55000), ("NL-CHANH", 8, 38000))),
            ("PN20261003", "Gia vị Việt", "HD-GV-077", (("NL-DAU", 30, 48000), ("NL-GIAVI", 12, 90000), ("NL-CAPHE", 8, 160000), ("NL-TRA", 5, 120000), ("NL-SUA", 20, 65000), ("NL-DUONG", 30, 24000), ("NL-KHUC-BACH", 10, 95000))),
            ("PN20261004", "Đồ uống Sài Gòn", "HD-DU-889", (("NL-NUOCNGOT", 240, 12000), ("NL-BIA", 240, 16000))),
        )
        for code, supplier_name, invoice_no, lines in receipt_specs:
            receipt = create_purchase_receipt(actor=actor, supplier_id=suppliers[supplier_name].pk, invoice_number=invoice_no, note="Đã kiểm đếm đủ và đạt chất lượng.")
            receipt.receipt_code = code
            receipt.save(update_fields=("receipt_code",))
            for ingredient_code, quantity, unit_cost in lines:
                add_purchase_line(actor=actor, receipt_id=receipt.pk, ingredient_id=ingredients[ingredient_code].pk,
                                  quantity=Decimal(quantity), unit_cost=Decimal(unit_cost))
            confirm_purchase_receipt(actor=actor, receipt_id=receipt.pk)
        draft = create_purchase_receipt(actor=actor, supplier_id=suppliers["Nông sản Xanh"].pk, invoice_number="DỰ KIẾN-209", note="Đơn dự kiến giao sáng mai; chưa cộng tồn.")
        draft.receipt_code = "PN20261005-NHAP"
        draft.save(update_fields=("receipt_code",))
        add_purchase_line(actor=actor, receipt_id=draft.pk, ingredient_id=ingredients["NL-RAU"].pk, quantity=Decimal(15), unit_cost=Decimal(33000))

        recipe_specs = {
            "KV01": (("NL-TOM", ".08"), ("NL-THIT-HEO", ".06"), ("NL-RAU", ".08"), ("NL-BUN", ".05")),
            "KV02": (("NL-TOM", ".10"), ("NL-THIT-HEO", ".05"), ("NL-DAU", ".04"), ("NL-RAU", ".05")),
            "MC01": (("NL-GAO", ".25"), ("NL-THIT-HEO", ".18"), ("NL-DAU", ".015"), ("NL-GIAVI", ".01"), ("NL-HANHTOI", ".01")),
            "MC02": (("NL-GAO", ".25"), ("NL-THIT-GA", ".22"), ("NL-DAU", ".03"), ("NL-GIAVI", ".01")),
            "MC03": (("NL-BUN", ".25"), ("NL-THIT-BO", ".15"), ("NL-RAU", ".06"), ("NL-GIAVI", ".012")),
            "MC04": (("NL-BUN", ".22"), ("NL-THIT-HEO", ".18"), ("NL-RAU", ".08"), ("NL-GIAVI", ".012")),
            "MC05": (("NL-TOM", ".25"), ("NL-GIAVI", ".02"), ("NL-DAU", ".02")),
            "MC06": (("NL-TRUNG", "2"), ("NL-THIT-HEO", ".08"), ("NL-DAU", ".015"), ("NL-HANHTOI", ".01")),
            "RAU01": (("NL-RAU", ".30"), ("NL-HANHTOI", ".025"), ("NL-DAU", ".015")),
            "RAU02": (("NL-RAU", ".35"), ("NL-GIAVI", ".01")),
            "DU01": (("NL-CAPHE", ".025"), ("NL-SUA", ".04")), "DU02": (("NL-TRA", ".012"), ("NL-CHANH", ".04"), ("NL-DUONG", ".03")),
            "DU03": (("NL-NUOCNGOT", "1"),), "DU04": (("NL-BIA", "1"),),
            "TM01": (("NL-TRAI-CAY", ".25"),), "TM02": (("NL-KHUC-BACH", ".18"), ("NL-SUA", ".03"), ("NL-DUONG", ".02")),
        }
        for dish_code, lines in recipe_specs.items():
            for ingredient_code, quantity in lines:
                RecipeIngredient.objects.create(dish=dishes[dish_code], ingredient=ingredients[ingredient_code], quantity=Decimal(quantity))

        PromotionCode.objects.create(code="WELCOME10", name="Chào khách mới", discount_type="PERCENT", value=10, minimum_order=150000, maximum_discount=50000, starts_at=now-timedelta(days=30), ends_at=now+timedelta(days=180))
        PromotionCode.objects.create(code="GIAM50K", name="Giảm 50.000đ hóa đơn lớn", discount_type="FIXED", value=50000, minimum_order=500000, starts_at=now-timedelta(days=10), ends_at=now+timedelta(days=90))
        PromotionCode.objects.create(code="HAPPY15", name="Ưu đãi 15%", discount_type="PERCENT", value=15, minimum_order=300000, maximum_discount=100000, starts_at=now-timedelta(days=3), ends_at=now+timedelta(days=30))

        BookingSettings.objects.create(pk=1, default_duration_minutes=120)
        for idx, status in enumerate((Booking.Status.COMPLETED, Booking.Status.CANCELLED, Booking.Status.NO_SHOW), start=1):
            start = now - timedelta(days=idx + 2, hours=2)
            Booking.objects.create(customer=customers[idx], table=tables[f"L0{idx}"], customer_name=customers[idx].full_name,
                                   customer_phone=customers[idx].phone, party_size=2+idx, starts_at=start,
                                   ends_at=start+timedelta(hours=2), status=status, created_by=actor,
                                   seated_at=start if status == Booking.Status.COMPLETED else None,
                                   completed_at=start+timedelta(hours=1, minutes=30) if status == Booking.Status.COMPLETED else None)

        def complete_order(table_code, customer, item_specs, days_ago, method, promo=None):
            order = order_services.open_table(actor=actor, table_id=tables[table_code].pk, guest_count=2, customer_id=customer.pk, note="Khách dùng bữa tại nhà hàng")
            order_services.add_items(actor=actor, order_id=order.pk, expected_revision=order.revision,
                                     items=[{"dish_id": dishes[code].pk, "quantity": qty, "note": note} for code, qty, note in item_specs])
            order.refresh_from_db()
            order_services.send_to_kitchen(actor=actor, order_id=order.pk, expected_revision=order.revision)
            for item in list(order.items.all()):
                for target in (OrderItem.Status.COOKING, OrderItem.Status.READY, OrderItem.Status.SERVED):
                    order.refresh_from_db()
                    order_services.transition_item(actor=actor, order_id=order.pk, item_id=item.pk, expected_revision=order.revision, target=target)
            order.refresh_from_db()
            order_services.request_payment(actor=actor, order_id=order.pk, expected_revision=order.revision)
            invoice = order_services.process_payment(actor=actor, order_id=order.pk, payment_method=method, transaction_code=f"GD-{order.pk:04d}", promotion_code=promo)
            closed = now - timedelta(days=days_ago, hours=days_ago % 3)
            Invoice.objects.filter(pk=invoice.pk).update(closed_at=closed, created_at=closed)
            Payment.objects.filter(invoice=invoice).update(created_at=closed)
            Order.objects.filter(pk=order.pk).update(opened_at=closed-timedelta(hours=1), closed_at=closed, created_at=closed-timedelta(hours=1))
            order_services.finish_cleaning(actor=actor, table_id=tables[table_code].pk)
            return order

        completed_specs = (
            ("T01", customers[0], (("MC01", 2, "Một phần ít mỡ"), ("RAU01", 1, ""), ("DU02", 2, "Ít đường")), 1, "CASH", "WELCOME10"),
            ("T02", customers[1], (("MC03", 2, "Một tô không hành"), ("KV01", 1, ""), ("DU03", 2, "")), 2, "BANK_TRANSFER", None),
            ("L01", customers[2], (("MC05", 1, "Ít cay"), ("MC04", 2, ""), ("RAU02", 1, ""), ("DU04", 5, "")), 3, "CASH", "GIAM50K"),
            ("T03", customers[3], (("MC02", 2, ""), ("KV02", 1, ""), ("TM02", 2, "")), 5, "BANK_TRANSFER", None),
            ("L02", customers[4], (("MC06", 2, ""), ("RAU01", 1, ""), ("DU01", 2, "")), 7, "CASH", None),
        )
        for spec in completed_specs:
            complete_order(*spec)

        open_order = order_services.open_table(actor=actor, table_id=tables["T01"].pk, guest_count=2, customer_id=customers[5].pk, note="Khách vừa vào bàn")
        order_services.add_item(actor=actor, order_id=open_order.pk, expected_revision=open_order.revision, dish_id=dishes["MC01"].pk, quantity=1, seat_number=1, note="Sườn ít mỡ")

        cooking_order = order_services.open_table(actor=actor, table_id=tables["T02"].pk, guest_count=3, customer_id=customers[6].pk, note="Bàn có trẻ em")
        order_services.add_items(actor=actor, order_id=cooking_order.pk, expected_revision=cooking_order.revision,
                                 items=[{"dish_id": dishes["MC02"].pk, "quantity": 2, "seat_number": 1, "note": ""}, {"dish_id": dishes["RAU02"].pk, "quantity": 1, "seat_number": None, "note": "Kho quẹt riêng"}])
        cooking_order.refresh_from_db(); order_services.send_to_kitchen(actor=actor, order_id=cooking_order.pk, expected_revision=cooking_order.revision)
        first_item = cooking_order.items.order_by("pk").first(); cooking_order.refresh_from_db()
        order_services.transition_item(actor=actor, order_id=cooking_order.pk, item_id=first_item.pk, expected_revision=cooking_order.revision, target=OrderItem.Status.COOKING)

        pay_order = order_services.open_table(actor=actor, table_id=tables["T03"].pk, guest_count=2, customer_id=customers[7].pk, note="Khách yêu cầu xuất hóa đơn")
        order_services.add_items(actor=actor, order_id=pay_order.pk, expected_revision=pay_order.revision,
                                 items=[{"dish_id": dishes["MC03"].pk, "quantity": 2, "note": ""}, {"dish_id": dishes["DU02"].pk, "quantity": 2, "note": ""}])
        pay_order.refresh_from_db(); order_services.send_to_kitchen(actor=actor, order_id=pay_order.pk, expected_revision=pay_order.revision)
        for item in list(pay_order.items.all()):
            for target in (OrderItem.Status.COOKING, OrderItem.Status.READY, OrderItem.Status.SERVED):
                pay_order.refresh_from_db(); order_services.transition_item(actor=actor, order_id=pay_order.pk, item_id=item.pk, expected_revision=pay_order.revision, target=target)
        pay_order.refresh_from_db(); order_services.request_payment(actor=actor, order_id=pay_order.pk, expected_revision=pay_order.revision)

        future_bookings = (
            (customers[8], "T04", 5, now+timedelta(hours=3), Booking.Status.CONFIRMED),
            (customers[9], "VIP01", 8, now+timedelta(days=1, hours=2), Booking.Status.PENDING),
        )
        for customer, table_code, party_size, start, status in future_bookings:
            Booking.objects.create(customer=customer, table=tables[table_code], customer_name=customer.full_name, customer_phone=customer.phone,
                                   party_size=party_size, starts_at=start, ends_at=start+timedelta(hours=2), status=status, created_by=actor)
            tables[table_code].status = DiningTable.Status.RESERVED
            tables[table_code].save(update_fields=("status", "updated_at"))

        stocktake = create_stocktake(actor=actor, note="Kiểm kê cuối tháng; đối chiếu toàn bộ kho.")
        actuals = {line.pk: line.ingredient.stock_quantity for line in stocktake.lines.select_related("ingredient")}
        vegetable_line = next(line for line in stocktake.lines.all() if line.ingredient_id == ingredients["NL-RAU"].pk)
        actuals[vegetable_line.pk] = max(Decimal("0"), vegetable_line.ingredient.stock_quantity - Decimal("0.300"))
        post_stocktake(actor=actor, stocktake_id=stocktake.pk, actual_quantities=actuals)
        record_waste(actor=actor, ingredient_id=ingredients["NL-HANHTOI"].pk, quantity=Decimal("0.200"), reason=WasteRecord.Reason.PREPARATION, note="Hao hụt sơ chế đầu ca")
        record_waste(actor=actor, ingredient_id=ingredients["NL-TRAI-CAY"].pk, quantity=Decimal("0.500"), reason=WasteRecord.Reason.SPOILED, note="Trái cây dập, loại bỏ")

        return {
            "users_preserved": User.objects.count(), "areas": Area.objects.count(), "tables": DiningTable.objects.count(),
            "customers": Customer.objects.count(), "dishes": Dish.objects.count(), "ingredients": Ingredient.objects.count(),
            "orders": Order.objects.count(), "paid_invoices": Invoice.objects.filter(status=Invoice.Status.PAID).count(),
            "bookings": Booking.objects.count(), "purchase_receipts": PurchaseReceipt.objects.count(),
        }
