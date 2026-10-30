"""One opt-in, minimal live connection check. Never prints credentials or SDK errors."""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
import sys

from apps.customer_portal.chatbot_gemini import ChatUnavailable, generate_reply


class Command(BaseCommand):
    help = "Gui mot yeu cau Gemini toi thieu, khong retry; chi in ket qua/nhom loi an toan."

    def handle(self, *args, **options):
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8")
        try:
            result = generate_reply({"restaurant": {"name": settings.RESTAURANT_PUBLIC_INFO["name"]}, "menu": [], "apriori": []}, [], "Xin chao nha hang.")
        except ChatUnavailable as error:
            reason = error.diagnostic or error.code
            advice = {
                "project_free_tier_unavailable": "Google xác nhận project hiện không được cấp Free Tier. Đổi key trong cùng project không sửa được lỗi này. Cần project có quyền Free Tier; giữ nguyên yêu cầu không bật billing.",
                "project_access_restricted": "Google đang hạn chế project. Kiểm tra trạng thái Free Tier của project trong AI Studio; tạo key mới trong cùng project không giải quyết hạn chế project. Không tự bật billing.",
                "permission_denied": "Google từ chối quyền sinh câu trả lời. Kiểm tra quyền key/project trong Google AI Studio; không tự bật billing.",
                "credential_reported_leaked": "Google báo key đã bị lộ. Thu hồi key cũ và cập nhật key mới trực tiếp trong .env; không gửi key qua chat.",
                "credential_invalid_or_expired": "Key không hợp lệ hoặc hết hạn. Cập nhật key trực tiếp trong .env.",
                "credential_service_restricted": "Kiểm tra API restriction của key với Generative Language API.",
                "credential_referrer_restricted": "Key bị giới hạn HTTP referrer, không phù hợp lời gọi từ máy chủ Django.",
                "credential_ip_restricted": "IP máy chủ chưa được cho phép trong giới hạn của key.",
                "api_service_disabled": "Kiểm tra Generative Language API đã được cho phép trong project của key.",
                "model_unavailable": "Model không khả dụng với lời gọi này. Chọn model có Free Tier và quyền truy cập phù hợp.",
            }.get(reason, error.message)
            raise CommandError(f"Gemini: {reason}. {advice}") from None
        self.stdout.write(self.style.SUCCESS(f"Gemini kết nối thành công: {settings.GEMINI_MODEL}; phản hồi JSON hợp lệ: {bool(result['answer'])}."))
