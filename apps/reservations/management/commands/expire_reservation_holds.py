from django.core.management.base import BaseCommand
from apps.reservations.services import expire_holds


class Command(BaseCommand):
    help="Giải phóng lịch/ nguyên liệu giữ chỗ chờ cọc đã hết hạn."

    def handle(self,*args,**options):
        self.stdout.write(f"Đã xử lý {expire_holds()} yêu cầu hết hạn.")
