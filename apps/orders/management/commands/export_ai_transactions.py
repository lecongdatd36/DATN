import csv
from datetime import date, datetime, time, timedelta
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from ai_tools.schema import TRANSACTION_FIELDS
from apps.orders.ai_export import transaction_rows


class Command(BaseCommand):
    help = "Xuất giỏ món đã thanh toán cho Apriori, không xuất tên/SĐT khách và không sửa database."

    def add_arguments(self, parser):
        parser.add_argument("--output", type=Path, default=Path("artifacts/ai/transactions.csv"))
        parser.add_argument("--date-from", type=date.fromisoformat)
        parser.add_argument("--date-to", type=date.fromisoformat)

    def handle(self, *args, **options):
        start, end = options["date_from"], options["date_to"]
        if start and end and start > end:
            raise CommandError("Ngày bắt đầu phải trước hoặc bằng ngày kết thúc.")
        bounds = {
            "start_at": timezone.make_aware(datetime.combine(start, time.min)) if start else None,
            "end_at": timezone.make_aware(datetime.combine(end + timedelta(days=1), time.min)) if end else None,
        }
        output = options["output"]
        baskets, count = set(), 0
        try:
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("x", encoding="utf-8-sig", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=TRANSACTION_FIELDS)
                writer.writeheader()
                for row in transaction_rows(**bounds):
                    writer.writerow(row)
                    baskets.add(row["basket_id"])
                    count += 1
        except OSError as error:
            raise CommandError(f"Không ghi được CSV (dùng tên mới nếu file đã có): {error}") from error
        self.stdout.write(self.style.SUCCESS(f"{len(baskets)} giỏ món, {count} dòng -> {output}"))
        self.stdout.write("Nguồn application_export chỉ xác nhận xuất từ ứng dụng; cần tự xác minh dữ liệu kinh doanh thực.")
