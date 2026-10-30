"""Explicit read-only public context. Never serialize model objects or internals."""
import unicodedata

from django.conf import settings
from django.urls import reverse

from apps.customers.models import MembershipTier
from apps.menu.models import Dish
from apps.menu.recommendations import dish_recommendations
from .selectors import customer_dishes


def public_restaurant(request):
    from .chatbot_service import provider_name
    return {"restaurant_public": settings.RESTAURANT_PUBLIC_INFO, "chat_provider_name": provider_name()}


def normalized(text):
    return " ".join("".join(c for c in unicodedata.normalize("NFKD", text.lower().replace("đ", "d"))
                            if not unicodedata.combining(c)).split())


def navigation_links():
    return [{"label": "Xem thực đơn", "url": reverse("customer_portal:menu")},
            {"label": "Đặt bàn", "url": reverse("customer_reservations:create")}]


def policy_reply(message):
    """Deterministic boundaries for actions, unverified facts and private data."""
    query = normalized(message)
    private_topic = any(word in query for word in ("doanh thu", "ton kho", "kho noi bo", "tai khoan noi bo", "danh sach tai khoan", "mat khau", "nhan vien nao", "danh sach nhan vien", "khach hang khac", "api key", "api_key", "system prompt", "system instruction"))
    # A question about a concept is different from a request for this restaurant's data.
    general_definition = any(phrase in query for phrase in ("la gi", "dinh nghia", "khai niem"))
    specific_access = any(phrase in query for phrase in ("nha hang", "qlnh", "com que", "noi bo", "cua toi", "dang dung", "hom nay", "thang nay", "cho xem", "in ra", "liet ke", "tat ca", "toan bo"))
    if private_topic and (not general_definition or specific_access):
        return "Mình có thể trò chuyện và giải thích thông tin công khai, nhưng không cung cấp dữ liệu nội bộ, tài khoản hoặc thông tin của người khác."
    if any(word in query for word in ("hang cua toi", "toi dang hang", "toi thuoc hang", "toi hang gi", "toi o hang", "hang theo so dien thoai", "tra hang theo")):
        return "Chatbot chưa xác minh danh tính nên không thể tra hạng hoặc tổng chi tiêu thực tế của bạn. Bạn hãy nhờ nhân viên kiểm tra hồ sơ; mình vẫn có thể giải thích các hạng và điều kiện lên hạng đang áp dụng."
    food_words = {"mon", "an", "com", "bun", "thit", "rau", "bep"}
    if ("di ung" in query or "an toan thuc pham" in query
            or ("thanh phan" in query and food_words.intersection(query.split()))):
        return "Hiện chưa có dữ liệu xác minh thành phần hoặc khả năng an toàn với dị ứng. Bạn hãy trao đổi trực tiếp với nhân viên trước khi gọi món; mình không thể cam kết món an toàn cho bạn."
    if any(word in query for word in ("dat ban", "giu cho", "con ban", "con cho")):
        return "Bạn hãy bấm Mở form đặt bàn, điền thông tin và gửi yêu cầu. Nhân viên sẽ kiểm tra và xác nhận. Chatbot chưa tạo đặt bàn và không xác nhận số bàn còn trống. Nếu đã gửi yêu cầu, bạn có thể dùng mục Tra cứu trên trang."
    facts = settings.RESTAURANT_PUBLIC_INFO
    if any(word in query for word in ("mo cua", "dong cua", "gio phuc vu")):
        return ("Giờ mở cửa được công bố: " + facts["opening_hours"]) if facts["opening_hours"] else "Giờ mở cửa của nhà hàng hiện chưa được cập nhật. Vui lòng liên hệ nhân viên để xác nhận."
    if "dia chi" in query:
        return ("Địa chỉ được công bố: " + facts["address"]) if facts["address"] else "Địa chỉ nhà hàng hiện chưa được cập nhật."
    if any(word in query for word in ("lien he", "so dien thoai", "email", "hotline")):
        values = [facts[key] for key in ("phone", "email") if facts[key]]
        return ("Liên hệ nhà hàng: " + "; ".join(values)) if values else "Số điện thoại và email liên hệ hiện chưa được cập nhật."
    return None


def public_context(message, history):
    # Reuse the public selector: active category + unit, AVAILABLE/SOLD_OUT only.
    records = list(customer_dishes().values("pk", "name", "price", "category__name", "unit__name", "status", "description")[:101])
    menu = [{"id": row["pk"], "name": row["name"], "price_vnd": str(row["price"]),
             "category": row["category__name"], "unit": row["unit__name"],
             "status": row["status"], "description": row["description"][:400]} for row in records[:100]]
    # Only tier definitions and benefits; never query Customer or its spending/history.
    tier_records = list(MembershipTier.objects.filter(is_active=True).order_by("minimum_spending", "pk")
                        .values("name", "minimum_spending", "discount_percent")[:51])
    tiers = [{"name": row["name"], "minimum_spending_vnd": str(row["minimum_spending"]),
              "discount_percent": str(row["discount_percent"])} for row in tier_records[:50]]
    available = {row["id"]: row for row in menu if row["status"] == Dish.Status.AVAILABLE}
    suggestions = []
    # Only attribute suggestions to Apriori when the existing service produces them.
    query = normalized(message)
    if any(phrase in query for phrase in ("goi them", "an them", "goi y them", "chon them")):
        selections = [message] + [item["text"] for item in reversed(history) if item["role"] == "user"]
        for selection in selections:
            selected = {pk for pk, row in available.items() if normalized(row["name"]) in normalized(selection)}
            if selected:
                suggestions = [available[item["id"]] for item in dish_recommendations(selected)
                               if item["id"] in available]
                break
    return {"restaurant": settings.RESTAURANT_PUBLIC_INFO, "menu": menu,
            "menu_truncated": len(records) > 100, "apriori": suggestions,
            "membership_tiers": tiers, "membership_tiers_truncated": len(tier_records) > 50,
            "membership_policy": {
                "basis": "Chi tiêu tích lũy từ tổng tiền thực tế của hóa đơn đã thanh toán gắn với hồ sơ khách.",
                "selection": "Chọn hạng đang áp dụng có mức chi tiêu tối thiểu cao nhất không vượt chi tiêu tích lũy.",
                "discount": "Ưu đãi hạng được tính trên tiền món khi thanh toán theo hạng tại thời điểm tính hóa đơn; không tự áp dụng hạng vừa dự kiến đạt vào hóa đơn đang tính.",
                "personal_lookup_available": False,
            }}, available
