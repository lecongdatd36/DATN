from pathlib import Path
from django.db import DatabaseError
from django.core.management.base import BaseCommand, CommandError
from core.database_backups import create_backup, verify_restore


class Command(BaseCommand):
    help = "Sao lưu PostgreSQL/SQL Server; tùy chọn kiểm chứng khôi phục vào database UUID riêng."

    def add_arguments(self, parser):
        parser.add_argument("--directory", type=Path)
        parser.add_argument("--verify-restore", action="store_true")
        parser.add_argument("--verify-file", type=Path)

    def handle(self, *args, **options):
        try:
            path = options["verify_file"] or create_backup(options["directory"])
            self.stdout.write(f"Backup: {path}")
            if options["verify_restore"] or options["verify_file"]:
                verify_restore(path)
                self.stdout.write(self.style.SUCCESS("Khôi phục vào database riêng thành công; database thử đã được xóa."))
        except (OSError, ValueError, KeyError, DatabaseError) as error:
            raise CommandError(str(error)) from None
