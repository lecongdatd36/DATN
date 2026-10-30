"""Check the selected remote provider once, using only a minimal public greeting."""
import sys

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.customer_portal.chatbot_service import ChatUnavailable, generate_reply, provider_name


class Command(BaseCommand):
    help = "Kiem tra mot lan ket noi API cua nha cung cap CHATBOT_PROVIDER, khong retry."

    def handle(self, *args, **options):
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8")
        try:
            result = generate_reply({"restaurant": {"name": "QLNH"}, "menu": [], "apriori": []}, [], "Xin chao nha hang.")
        except ChatUnavailable as error:
            raise CommandError(f"{provider_name()}: {error.diagnostic or error.code}. {error.message}") from None
        model = settings.GROQ_MODEL if settings.CHATBOT_PROVIDER == "groq" else settings.GEMINI_MODEL
        self.stdout.write(self.style.SUCCESS(f"{provider_name()} kết nối thành công: {model}; JSON hợp lệ: {bool(result['answer'])}."))
