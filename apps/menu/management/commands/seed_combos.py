from decimal import Decimal, ROUND_HALF_UP
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from apps.menu.combos import save_combo
from apps.menu.models import Combo, Dish


class Command(BaseCommand):
    help = "Create three Cơm Quê starter combos; never overwrite existing combos or orders."

    def add_arguments(self, parser):
        parser.add_argument("--actor", help="Manager username for the catalog audit log")

    def handle(self, *args, **options):
        users = get_user_model().objects.filter(is_active=True)
        actor = users.filter(username=options["actor"]).first() if options.get("actor") else users.filter(is_superuser=True).first()
        if not actor:
            raise CommandError("Cần tài khoản quản lý qua --actor để ghi nhật ký tạo combo.")
        plans = [
            ("CB_HENHO", "Hẹn hò vị nhà", 2, "Một bữa ngon cho hai người, đủ món chính và trà mát.", [("Cơm gà xối mỡ",1),("Cơm sườn nướng",1),("Trà chanh",2)]),
            ("CB_SUMVAY", "Sum vầy bốn người", 4, "Cơm nóng, món giòn và chút trà cho cả nhà ngồi lại.", [("Cơm gà xối mỡ",2),("Cơm sườn nướng",2),("Chả giò hải sản",1),("Trà chanh",4)]),
            ("CB_BANBE", "Bạn bè quây quần", 6, "Bữa hẹn đông vui với cơm, gỏi cuốn và trà chanh.", [("Cơm gà xối mỡ",3),("Cơm sườn nướng",3),("Gỏi cuốn tôm thịt",2),("Trà chanh",6)]),
        ]
        for code,name,people,description,parts in plans:
            if Combo.objects.filter(code=code).exists():
                self.stdout.write(f"Giữ nguyên combo đã có: {code}")
                continue
            items,regular = [],Decimal(0)
            for dish_name,quantity in parts:
                dish = Dish.objects.filter(name=dish_name,status="AVAILABLE").first()
                if not dish:
                    break
                items.append({"dish_id":dish.pk,"quantity":quantity})
                regular += dish.price*quantity
            else:
                price=(regular*Decimal('.9')/1000).quantize(Decimal(1),rounding=ROUND_HALF_UP)*1000
                row=save_combo(actor=actor,code=code,name=name,people=people,description=description,price=price,is_active=True,items=items)
                self.stdout.write(f"Đã tạo {row.code}: {row.price}đ ({people} người)")
                continue
            self.stdout.write(f"Bỏ qua {code}: chưa đủ món thành phần đang bán.")
