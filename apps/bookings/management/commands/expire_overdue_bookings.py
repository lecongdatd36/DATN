from django.core.management.base import BaseCommand

from apps.bookings.services import expire_overdue_bookings


class Command(BaseCommand):
    help = "Đánh dấu lịch quá thời gian chờ là không đến và đồng bộ trạng thái bàn."

    def handle(self, *args, **options):
        expired_count = expire_overdue_bookings()
        self.stdout.write(self.style.SUCCESS(f"Đã xử lý {expired_count} lịch không đến."))
