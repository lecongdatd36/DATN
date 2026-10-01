from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.inventory.models import PurchaseReceipt, Stocktake, Supplier, WasteRecord
from apps.inventory.services import (
    add_purchase_line, cancel_purchase_receipt, confirm_purchase_receipt,
    create_purchase_receipt, create_stocktake, post_stocktake, record_waste,
)


class Command(BaseCommand):
    help = "Tạo dữ liệu trình diễn đầy đủ cho luồng nhập hàng, kiểm kê và hao hụt."

    @transaction.atomic
    def handle(self, *args, **options):
        call_command("seed_inventory_starter", attach_first_dish=True, verbosity=0)
        actor = get_user_model().objects.filter(is_superuser=True, is_active=True).order_by("pk").first()
        if actor is None:
            raise ValidationError("Cần có một tài khoản quản trị đang hoạt động để tạo dữ liệu mẫu.")

        suppliers = {}
        for name, phone, address in (
            ("Thực phẩm An Phú", "0901000001", "12 Nguyễn Văn Linh"),
            ("Nông sản Xanh", "0901000002", "45 Quốc lộ 1A"),
            ("Gia vị Việt", "0901000003", "18 Lê Văn Việt"),
        ):
            suppliers[name], _ = Supplier.objects.get_or_create(
                name=name, defaults={"phone": phone, "address": address, "is_active": True},
            )

        from apps.inventory.models import Ingredient
        ingredients = Ingredient.objects.in_bulk(field_name="code")

        if not PurchaseReceipt.objects.filter(receipt_code="PN-DEMO-DA-NHAN").exists():
            receipt = create_purchase_receipt(
                actor=actor, supplier_id=suppliers["Thực phẩm An Phú"].pk,
                invoice_number="HDAP-2026-001", note="Phiếu mẫu đã nhận đủ hàng và đối chiếu hóa đơn.",
            )
            receipt.receipt_code = "PN-DEMO-DA-NHAN"
            receipt.save(update_fields=("receipt_code",))
            for code, quantity, unit_cost in (
                ("NL-THIT-HEO", "5", "105000"),
                ("NL-GAO", "20", "22000"),
                ("NL-DAU-AN", "5", "48000"),
            ):
                add_purchase_line(
                    actor=actor, receipt_id=receipt.pk, ingredient_id=ingredients[code].pk,
                    quantity=Decimal(quantity), unit_cost=Decimal(unit_cost),
                )
            confirm_purchase_receipt(actor=actor, receipt_id=receipt.pk)

        if not PurchaseReceipt.objects.filter(receipt_code="PN-DEMO-NHAP").exists():
            receipt = create_purchase_receipt(
                actor=actor, supplier_id=suppliers["Nông sản Xanh"].pk,
                invoice_number="NSX-DU-KIEN-002", note="Phiếu mẫu đang chờ giao hàng vào sáng mai.",
            )
            receipt.receipt_code = "PN-DEMO-NHAP"
            receipt.save(update_fields=("receipt_code",))
            for code, quantity, unit_cost in (
                ("NL-RAU-CU", "8", "32000"),
                ("NL-TRUNG", "60", "3200"),
            ):
                add_purchase_line(
                    actor=actor, receipt_id=receipt.pk, ingredient_id=ingredients[code].pk,
                    quantity=Decimal(quantity), unit_cost=Decimal(unit_cost),
                )

        if not PurchaseReceipt.objects.filter(receipt_code="PN-DEMO-DA-HUY").exists():
            receipt = create_purchase_receipt(
                actor=actor, supplier_id=suppliers["Gia vị Việt"].pk,
                invoice_number="GV-HUY-003", note="Phiếu mẫu bị hủy do nhà cung cấp giao sai quy cách.",
            )
            receipt.receipt_code = "PN-DEMO-DA-HUY"
            receipt.save(update_fields=("receipt_code",))
            add_purchase_line(
                actor=actor, receipt_id=receipt.pk, ingredient_id=ingredients["NL-GIA-VI"].pk,
                quantity=Decimal("3"), unit_cost=Decimal("85000"),
            )
            cancel_purchase_receipt(actor=actor, receipt_id=receipt.pk)

        if not Stocktake.objects.filter(stocktake_code="KK-DEMO-DA-CHOT").exists():
            if not Stocktake.objects.filter(status=Stocktake.Status.DRAFT).exists():
                stocktake = create_stocktake(actor=actor, note="Kiểm kê mẫu cuối ca; số thực tế khớp hệ thống.")
                stocktake.stocktake_code = "KK-DEMO-DA-CHOT"
                stocktake.save(update_fields=("stocktake_code",))
                post_stocktake(
                    actor=actor, stocktake_id=stocktake.pk,
                    actual_quantities={line.pk: line.ingredient.stock_quantity for line in stocktake.lines.select_related("ingredient")},
                )

        if not WasteRecord.objects.filter(waste_code="HH-DEMO-RAU").exists():
            waste = record_waste(
                actor=actor, ingredient_id=ingredients["NL-RAU-CU"].pk,
                quantity=Decimal("0.500"), reason=WasteRecord.Reason.SPOILED,
                note="Rau dập, không đạt chất lượng đầu ca.",
            )
            waste.waste_code = "HH-DEMO-RAU"
            waste.save(update_fields=("waste_code",))
        if not WasteRecord.objects.filter(waste_code="HH-DEMO-SO-CHE").exists():
            waste = record_waste(
                actor=actor, ingredient_id=ingredients["NL-HANH-TOI"].pk,
                quantity=Decimal("0.200"), reason=WasteRecord.Reason.PREPARATION,
                note="Vỏ và phần loại bỏ trong sơ chế.",
            )
            waste.waste_code = "HH-DEMO-SO-CHE"
            waste.save(update_fields=("waste_code",))

        self.stdout.write(self.style.SUCCESS("Inventory workflow demo data is ready; existing demo records were preserved."))
