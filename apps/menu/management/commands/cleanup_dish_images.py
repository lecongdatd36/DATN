"""Collect old unused UUID images, including files left by an outer rollback."""
from datetime import timedelta
import re
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from core.menu_lock import lock_menu
from apps.menu.models import Dish


class Command(BaseCommand):
    help = "Liệt kê ảnh món không còn được dùng, cũ hơn 24 giờ. Chỉ xóa khi có --delete."

    def add_arguments(self, parser):
        parser.add_argument("--delete", action="store_true", help="Xóa các tệp dư thừa đã kiểm tra.")

    def handle(self, *args, **options):
        storage = Dish._meta.get_field("image").storage
        count = 0
        with transaction.atomic():
            lock_menu()
            references = {name for pair in Dish.objects.values_list("image", "thumbnail") for name in pair if name}
            try:
                _, filenames = storage.listdir("dishes")
            except FileNotFoundError:
                filenames = []
            for filename in filenames:
                if not re.fullmatch(r"[0-9a-f]{32}-(main|thumb)\.webp", filename):
                    continue
                name = f"dishes/{filename}"
                if name in references or storage.get_modified_time(name) >= timezone.now() - timedelta(hours=24):
                    continue
                self.stdout.write(name)
                if options["delete"]:
                    storage.delete(name)
                count += 1
        self.stdout.write(f"{'Đã xóa' if options['delete'] else 'Tệp có thể dọn'}: {count}")
