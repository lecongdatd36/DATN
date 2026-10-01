from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.inventory.models import Ingredient, InventoryTransaction, RecipeIngredient, Supplier
from apps.menu.models import Dish


STARTER_INGREDIENTS = (
    ("NL-THIT-HEO", "Thịt heo", "kg", "20", "100000", "3"),
    ("NL-GAO", "Gạo", "kg", "50", "20000", "10"),
    ("NL-DAU-AN", "Dầu ăn", "lít", "10", "45000", "2"),
    ("NL-RAU-CU", "Rau củ", "kg", "15", "30000", "3"),
    ("NL-GIA-VI", "Gia vị tổng hợp", "kg", "5", "80000", "1"),
    ("NL-TRUNG", "Trứng", "quả", "100", "3000", "20"),
    ("NL-NUOC-MAM", "Nước mắm", "lít", "8", "60000", "1"),
    ("NL-HANH-TOI", "Hành và tỏi", "kg", "4", "40000", "1"),
)


class Command(BaseCommand):
    help = "Tạo bộ nguyên liệu và tồn đầu kỳ tối thiểu để bắt đầu khai báo công thức món."

    def add_arguments(self, parser):
        parser.add_argument(
            "--attach-first-dish",
            action="store_true",
            help="Gắn công thức mẫu vào món đầu tiên nếu món đó chưa có công thức.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        Supplier.objects.get_or_create(
            name="Nhà cung cấp mặc định",
            defaults={"phone": "", "address": "Cập nhật thông tin nhà cung cấp thực tế"},
        )
        actor = get_user_model().objects.filter(is_superuser=True, is_active=True).order_by("pk").first()
        created_count = 0
        for code, name, unit, opening_stock, unit_cost, threshold in STARTER_INGREDIENTS:
            ingredient, created = Ingredient.objects.get_or_create(
                code=code,
                defaults={
                    "name": name,
                    "unit": unit,
                    "stock_quantity": Decimal(opening_stock),
                    "average_unit_cost": Decimal(unit_cost),
                    "low_stock_threshold": Decimal(threshold),
                },
            )
            if not created:
                continue
            created_count += 1
            InventoryTransaction.objects.create(
                ingredient=ingredient,
                transaction_type=InventoryTransaction.Type.IMPORT,
                quantity=ingredient.stock_quantity,
                stock_before=Decimal("0"),
                stock_after=ingredient.stock_quantity,
                unit_cost=ingredient.average_unit_cost,
                note="Tồn đầu kỳ từ bộ dữ liệu khởi tạo; cần đối chiếu và điều chỉnh theo tồn thực tế.",
                performed_by=actor,
            )
        recipe_count = 0
        if options["attach_first_dish"]:
            dish = Dish.objects.order_by("pk").first()
            if dish and not dish.recipe_ingredients.exists():
                sample_lines = (
                    ("NL-THIT-HEO", "0.250"),
                    ("NL-DAU-AN", "0.020"),
                    ("NL-GIA-VI", "0.010"),
                    ("NL-HANH-TOI", "0.020"),
                )
                ingredients = Ingredient.objects.in_bulk(field_name="code")
                for code, quantity in sample_lines:
                    if code in ingredients:
                        RecipeIngredient.objects.create(
                            dish=dish,
                            ingredient=ingredients[code],
                            quantity=Decimal(quantity),
                        )
                        recipe_count += 1
        self.stdout.write(self.style.SUCCESS(
            f"Created {created_count} ingredients and {recipe_count} sample recipe lines; existing data was preserved."
        ))
