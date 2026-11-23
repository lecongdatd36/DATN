"""Generate a Vietnamese schema specification from models and read-only PostgreSQL catalogs.

No business rows or credentials are exported. Existing ERD files are left intact.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, time
from decimal import Decimal
from html import escape
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "QLNH.settings")
import django
django.setup()

from django.apps import apps
from django.db import connection, transaction
from django.db.models import NOT_PROVIDED
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

OUTPUT = ROOT / "docs"
GROUPS = [
    ("accounts", "Tài khoản và nhóm quyền"),
    ("employees", "Hồ sơ nhân viên"),
    ("customers", "Khách hàng và hạng thành viên"),
    ("seating", "Khu vực, bàn và mã QR"),
    ("bookings", "Lịch đặt và lượt khách"),
    ("reservations", "Đặt bàn online, món đặt trước và tiền cọc"),
    ("menu", "Thực đơn và combo"),
    ("orders", "Gọi món, hóa đơn, thanh toán và yêu cầu QR"),
    ("inventory", "Kho nguyên liệu"),
    ("workforce", "Ca làm và chấm công"),
    ("technical", "Bảng kỹ thuật và phân quyền Django"),
]

# Title and role are intentionally maintained as business documentation.
DESCRIPTIONS = {
    "accounts.User": ("Tài khoản", "Lưu thông tin xác thực tài khoản nội bộ, trạng thái hoạt động và phiên bản phiên đăng nhập."),
    "accounts.SecurityRateBucket": ("Giới hạn tần suất truy cập", "Bộ đếm dùng chung theo cửa sổ thời gian; khóa HMAC không chứa tài khoản hoặc IP dạng rõ."),
    "accounts.User_groups": ("Tài khoản – nhóm quyền", "Bảng nối nhiều–nhiều giữa tài khoản nội bộ và nhóm quyền."),
    "accounts.User_user_permissions": ("Quyền riêng của tài khoản", "Bảng nối các quyền được gán trực tiếp cho từng tài khoản."),
    "employees.JobPosition": ("Chức vụ", "Danh mục chức vụ liên kết với nhóm quyền Django."),
    "employees.EmployeeProfile": ("Hồ sơ nhân viên", "Thông tin nhân sự, chức vụ, trạng thái làm việc và tài khoản liên kết."),
    "employees.EmployeeActivityLog": ("Nhật ký nhân viên", "Lưu thao tác quản lý nhân sự và thông tin tại thời điểm thay đổi."),
    "customers.MembershipTier": ("Hạng thành viên", "Ngưỡng chi tiêu và mức ưu đãi của từng hạng khách hàng."),
    "customers.Customer": ("Khách hàng", "Hồ sơ khách hàng, tổng chi tiêu và hạng thành viên hiện tại."),
    "customers.CustomerActivityLog": ("Nhật ký khách hàng", "Theo dõi thay đổi hồ sơ và hạng của khách hàng."),
    "seating.Area": ("Khu vực", "Danh mục các khu vực phục vụ trong nhà hàng."),
    "seating.DiningTable": ("Bàn", "Mã bàn, khu vực, sức chứa và trạng thái vận hành."),
    "seating.DiningTableQRToken": ("Mã QR bàn", "Token truy cập các chức năng tự phục vụ của khách tại bàn."),
    "seating.SeatingActivityLog": ("Nhật ký bàn và khu vực", "Lịch sử thay đổi bàn/khu vực; đối tượng được nhận diện bằng loại và mã tham chiếu."),
    "bookings.Booking": ("Lịch đặt và lượt khách", "Ghi nhận bàn, khoảng thời gian dự kiến, khách đến và tiến trình phục vụ; hỗ trợ khách không đặt trước."),
    "bookings.BookingActivityLog": ("Nhật ký lịch đặt", "Ghi nhận tạo, thay đổi trạng thái và chuyển bàn của lịch đặt/lượt khách."),
    "bookings.BookingSettings": ("Cấu hình đặt bàn", "Cấu hình giờ phục vụ, thời lượng mặc định và thời gian chờ khách; giới hạn khóa chính bằng 1."),
    "bookings.BookingSettingsLog": ("Nhật ký cấu hình đặt bàn", "Lưu các giá trị cấu hình trước và sau khi thay đổi."),
    "reservations.ReservationPolicy": ("Chính sách đặt online", "Mức cọc, thời gian giữ chỗ và chính sách món chuẩn bị trước; giới hạn khóa chính bằng 1."),
    "reservations.ReservationPolicy_allowed_dishes": ("Món được chuẩn bị trước", "Bảng nối chính sách đặt online với danh sách món được phép chuẩn bị trước."),
    "reservations.Reservation": ("Yêu cầu đặt online", "Yêu cầu đặt của khách, thông tin bản chốt, lịch chuẩn bị, mức cọc và liên kết lượt khách khi được bố trí bàn."),
    "reservations.PreorderItem": ("Món đặt trước", "Lưu món/combo đặt trước và snapshot giá; có thể liên kết dòng món khi nhận khách."),
    "reservations.IngredientHold": ("Giữ nguyên liệu", "Định lượng nguyên liệu cam kết cho món đặt trước, cùng trạng thái giữ, xuất hoặc giải phóng."),
    "reservations.DepositPayment": ("Thanh toán cọc", "Giao dịch trả cọc của một yêu cầu đặt online, gồm khoản cần đối soát."),
    "reservations.DepositAllocation": ("Khấu trừ cọc", "Phân bổ cọc vào một hóa đơn, ngăn cộng tiền cọc lần nữa khi thu phần còn lại."),
    "reservations.DepositRefund": ("Hoàn cọc", "Yêu cầu, duyệt và ghi nhận hoàn cọc với bằng chứng giao dịch."),
    "reservations.ReservationMessage": ("Yêu cầu thay đổi/hủy", "Tin nhắn khách gửi cho nhà hàng về việc sửa hoặc hủy đặt online."),
    "reservations.ReservationLog": ("Nhật ký đặt online", "Lịch sử xử lý yêu cầu, cọc, món chuẩn bị trước và nhận khách."),
    "menu.Category": ("Danh mục món", "Phân nhóm món ăn và trạng thái sử dụng của danh mục."),
    "menu.Unit": ("Đơn vị bán", "Danh mục đơn vị tính dùng khi bán món."),
    "menu.Dish": ("Món ăn", "Thông tin món, giá bán, ảnh, bản dịch, trạng thái bán và cờ theo dõi kho."),
    "menu.Combo": ("Combo", "Thông tin bộ món bán theo combo và giá áp dụng."),
    "menu.ComboItem": ("Thành phần combo", "Danh sách món và số lượng trong mỗi combo."),
    "menu.MenuActivityLog": ("Nhật ký thực đơn", "Lịch sử thay đổi thực đơn; lưu loại đối tượng và mã tham chiếu."),
    "orders.PromotionCode": ("Mã khuyến mãi", "Điều kiện, thời hạn và mức giảm của chương trình khuyến mãi."),
    "orders.Order": ("Đơn hàng", "Ghi nhận lượt gọi món, bàn, khách, nhân viên, số tiền và quan hệ đơn gốc/đơn con khi tách thanh toán."),
    "orders.OrderItem": ("Chi tiết đơn hàng", "Dòng món có snapshot tên, đơn vị, giá bán, giá vốn và các mốc xử lý tại bếp."),
    "orders.Invoice": ("Hóa đơn", "Chứng từ tính tiền cho một đơn hàng, lưu giảm giá, tổng phải thu, đã thu và trạng thái."),
    "orders.CashShift": ("Ca thu ngân", "Theo dõi tiền đầu ca, các phiếu thu/hoàn gắn ca, thực đếm, chênh lệch và xác nhận bàn giao."),
    "orders.InvoiceRefund": ("Phiếu hoàn hóa đơn", "Yêu cầu, duyệt và ghi nhận khoản hoàn thực tế theo phiếu thu gốc."),
    "orders.PaymentReconciliation": ("Kết quả đối soát thanh toán", "Ghi nhận xử lý khoản ZaloPay đã xác minh: áp dụng, khớp phiếu thu hoặc hoàn khoản thừa."),
    "orders.FinanceLog": ("Nhật ký thu ngân", "Lịch sử thao tác ca thu ngân, hoàn tiền và đối soát."),
    "orders.PaymentBatch": ("Đợt thanh toán nhiều bàn", "Nhóm các phiếu thu của một thao tác thanh toán nhiều đơn/bàn."),
    "orders.Payment": ("Phiếu thu", "Số tiền thu hoặc khấu trừ cọc cho hóa đơn và thông tin người thực hiện."),
    "orders.OnlinePayment": ("Thanh toán trực tuyến cho đơn", "Theo dõi giao dịch trực tuyến của đơn và snapshot số tiền, ưu đãi tại thời điểm tạo."),
    "orders.ZaloPayTransaction": ("Giao dịch ZaloPay", "Thông tin giao tiếp ZaloPay Sandbox, liên kết thanh toán đơn hoặc tiền cọc và trạng thái đối soát."),
    "orders.OrderActivityLog": ("Nhật ký đơn hàng", "Lưu thao tác gọi món, bếp, thanh toán và xử lý đơn."),
    "orders.PaymentRequest": ("Yêu cầu thanh toán", "Yêu cầu chuyển đơn sang quy trình thu tiền và trạng thái xử lý."),
    "orders.QRCheckInRequest": ("Yêu cầu nhận bàn QR", "Khách đề nghị nhận bàn qua QR, chờ nhân viên xác nhận hoặc từ chối."),
    "orders.QROrderRequest": ("Yêu cầu gọi món QR", "Giỏ món khách gửi từ bàn, được nhân viên xác nhận vào đơn."),
    "orders.QRServiceRequest": ("Yêu cầu phục vụ QR", "Các yêu cầu phục vụ của khách tại bàn và thông tin hoàn tất."),
    "orders.QROrderRequestItem": ("Chi tiết gọi món QR", "Dòng món đề nghị qua QR, snapshot giá và liên kết dòng đơn sau xác nhận."),
    "inventory.Supplier": ("Nhà cung cấp", "Thông tin liên hệ và trạng thái hợp tác với nhà cung cấp."),
    "inventory.Ingredient": ("Nguyên liệu", "Danh mục nguyên liệu, đơn vị kho, tồn, giá vốn bình quân và ngưỡng cảnh báo."),
    "inventory.InventoryTransaction": ("Giao dịch kho", "Sổ biến động nguyên liệu gồm số lượng, tồn trước/sau và tham chiếu nguồn nghiệp vụ."),
    "inventory.RecipeIngredient": ("Định mức món", "Bảng nối món–nguyên liệu, lưu lượng nguyên liệu cho một đơn vị món."),
    "inventory.PurchaseReceipt": ("Phiếu nhập hàng", "Chứng từ mua/nhận nguyên liệu từ nhà cung cấp và trạng thái xác nhận."),
    "inventory.PurchaseReceiptLine": ("Chi tiết nhập hàng", "Nguyên liệu, số lượng và đơn giá từng dòng phiếu nhập."),
    "inventory.Stocktake": ("Phiếu kiểm kê", "Thông tin lập và chốt đợt kiểm kê kho."),
    "inventory.StocktakeLine": ("Chi tiết kiểm kê", "Tồn hệ thống và số lượng thực đếm theo nguyên liệu trong kỳ kiểm kê."),
    "inventory.WasteRecord": ("Phiếu hao hụt", "Ghi nhận nguyên liệu hao hụt, nguyên nhân và snapshot giá vốn."),
    "workforce.WorkShift": ("Ca làm", "Danh mục giờ ca, thời gian nghỉ và mức trễ cho phép."),
    "workforce.WorkSchedule": ("Lịch làm việc", "Phân ca cho nhân viên vào một ngày; lưu snapshot khung giờ và chính sách ca."),
    "workforce.Attendance": ("Bản ghi chấm công", "Giờ vào/ra thực tế, điều chỉnh và duyệt công của một lịch làm việc."),
    "workforce.FaceProfile": ("Mẫu khuôn mặt", "Vector đặc trưng nhận diện, phiên bản mô hình và thời điểm đồng ý đăng ký của nhân viên."),
    "workforce.KioskDevice": ("Thiết bị chấm công", "Thiết bị được kích hoạt, token đã băm, thời hạn và trạng thái sử dụng."),
    "workforce.FaceChallenge": ("Lượt xác minh khuôn mặt", "Tiến trình xác minh tư thế và nguồn phiên/thiết bị cho một lần chấm công."),
    "workforce.AttendanceLog": ("Nhật ký chấm công", "Theo dõi thao tác nhân sự, lịch công và thiết bị liên quan."),
    "auth.Group": ("Nhóm quyền", "Danh mục nhóm quyền dùng cho tài khoản nội bộ và chức vụ."),
    "auth.Permission": ("Quyền", "Danh mục quyền theo loại đối tượng Django."),
    "auth.Group_permissions": ("Quyền của nhóm", "Bảng nối nhiều–nhiều giữa nhóm và quyền."),
    "contenttypes.ContentType": ("Loại đối tượng Django", "Định danh app/model dùng cho quyền và nhật ký quản trị."),
    "admin.LogEntry": ("Nhật ký quản trị Django", "Nhật ký thao tác của Django Admin; object_id là tham chiếu đa hình, không phải FK đến mọi bảng nghiệp vụ."),
    "sessions.Session": ("Phiên đăng nhập", "Dữ liệu phiên Django được tuần tự hóa và ký xác thực; nội dung không được mã hóa bảo mật bởi cơ chế ký này."),
    "django_migrations": ("Lịch sử migration", "Ghi nhận các migration đã áp dụng cho cơ sở dữ liệu."),
    "qlnh_chatbot_cache": ("Bộ nhớ đệm chatbot", "Lưu trạng thái hội thoại và bộ đếm giới hạn tần suất có thời hạn dùng chung giữa các tiến trình."),
}

LABELS = {
    "id": "Định danh bản ghi", "created_at": "Thời điểm tạo", "updated_at": "Thời điểm cập nhật",
    "created_by": "Tài khoản tạo", "performed_by": "Tài khoản thực hiện", "actor": "Tài khoản thao tác",
    "actor_snapshot": "Tên người thực hiện tại thời điểm ghi nhận", "user": "Tài khoản", "employee": "Nhân viên",
    "group": "Nhóm quyền", "permission": "Quyền", "name": "Tên", "code": "Mã nghiệp vụ", "description": "Nội dung mô tả",
    "revision": "Phiên bản bản ghi dùng kiểm tra cập nhật đồng thời", "session_version": "Phiên bản xác thực để vô hiệu hóa phiên cũ",
    "status": "Trạng thái xử lý", "note": "Ghi chú", "full_name": "Họ tên", "phone": "Số điện thoại",
    "accepted_at": "Thời điểm khách đồng ý bản chốt", "access_token": "Token truy cập riêng yêu cầu đặt online",
    "action": "Thao tác", "amount": "Số tiền", "app_id": "Mã ứng dụng ZaloPay", "app_trans_id": "Mã giao dịch phía ứng dụng gửi ZaloPay",
    "app_label": "Tên ứng dụng Django", "approved_at": "Thời điểm duyệt", "approved_by": "Tài khoản duyệt",
    "area": "Khu vực", "attempts": "Số lần thử xác minh", "bank_reference": "Mã/bằng chứng giao dịch hoàn",
    "batch": "Đợt thanh toán nhiều bàn", "booking": "Lịch đặt/lượt khách", "break_minutes": "Số phút nghỉ không tính công",
    "cancelled_at": "Thời điểm hủy", "client_request_id": "Định danh yêu cầu từ phía khách để chống gửi lặp",
    "combo": "Combo", "combo_name": "Tên combo tại thời điểm đặt", "combo_snapshot": "Thông tin combo tại thời điểm đặt",
    "completed_at": "Thời điểm hoàn tất", "completed_by": "Tài khoản hoàn tất", "confirmed_at": "Thời điểm xác nhận",
    "confirmed_by": "Tài khoản xác nhận", "consent_at": "Thời điểm đồng ý đăng ký nhận diện", "customer": "Khách hàng",
    "deposit_payment": "Giao dịch trả cọc", "deposit_required": "Số tiền cọc yêu cầu", "device": "Thiết bị chấm công",
    "dish": "Món ăn", "dish_code": "Mã món tại thời điểm ghi nhận", "dish_name": "Tên món tại thời điểm ghi nhận",
    "duration_minutes": "Thời lượng dự kiến (phút)", "embeddings": "Danh sách vector đặc trưng khuôn mặt",
    "enrolled_by": "Tài khoản đăng ký mẫu", "expires_at": "Thời điểm hết hạn", "frame_hashes": "Mã băm khung hình để phát hiện ảnh lặp",
    "free_cancel_until": "Hạn hủy miễn phí", "grace_minutes": "Số phút trễ cho phép", "guest_count": "Số khách",
    "hold_expires_at": "Hạn giữ chỗ chờ thanh toán cọc", "ingredient": "Nguyên liệu",
    "inventory_deducted_at": "Thời điểm đã trừ nguyên liệu", "inventory_returned_at": "Thời điểm đã hoàn nguyên liệu",
    "invoice": "Hóa đơn", "is_active": "Cờ còn hiệu lực/đang sử dụng", "is_automatic": "Cờ tự xác định thao tác vào/ra ca",
    "item": "Dòng món đặt trước", "kind": "Loại yêu cầu", "last_attempt_at": "Thời điểm thử xác minh gần nhất",
    "last_error": "Thông tin lỗi hoặc yêu cầu đối soát gần nhất", "last_queried_at": "Thời điểm truy vấn cổng gần nhất",
    "mode": "Phương thức phục vụ yêu cầu đặt online", "model_version": "Phiên bản mô hình nhận diện",
    "neutral_yaw": "Góc quay ngang đầu ở tư thế chuẩn", "new_hours": "Khung giờ sau thay đổi",
    "new_minutes": "Thời lượng sau thay đổi (phút)", "new_no_show_grace_minutes": "Mức chờ khách sau thay đổi (phút)",
    "object_id": "Mã đối tượng được ghi nhật ký", "offer_expires_at": "Hạn hiệu lực bản chốt",
    "order": "Đơn hàng", "order_item": "Dòng món trong đơn", "order_payment": "Thanh toán trực tuyến của đơn",
    "order_revision": "Phiên bản đơn lúc tạo giao dịch", "order_url": "Đường dẫn mở cổng thanh toán",
    "paid_at": "Thời điểm xác nhận đã thu", "party_size": "Số khách", "policy_snapshot": "Chính sách tại thời điểm đặt",
    "poses": "Chuỗi tư thế cần xác minh", "posted_at": "Thời điểm chốt", "posted_by": "Tài khoản chốt",
    "prep_starts_at": "Giờ dự kiến bắt đầu chuẩn bị", "previous_hours": "Khung giờ trước thay đổi",
    "previous_minutes": "Thời lượng trước thay đổi (phút)", "previous_no_show_grace_minutes": "Mức chờ khách trước thay đổi (phút)",
    "processed_at": "Thời điểm xử lý", "profile_version": "Thời điểm cập nhật mẫu khuôn mặt dùng cho lượt xác minh",
    "provider_ref": "Mã giao dịch phía cổng", "quantity": "Số lượng", "ready_at": "Thời điểm món sẵn sàng",
    "ready_by": "Hạn cần chuẩn bị xong", "reason": "Lý do", "receipt": "Phiếu nhập hàng", "received_at": "Thời điểm nhận hàng",
    "recorded_by": "Tài khoản ghi nhận", "reject_reason": "Lý do từ chối", "rejected_at": "Thời điểm từ chối",
    "rejected_by": "Tài khoản từ chối", "request": "Yêu cầu gọi món QR", "request_data": "Dữ liệu yêu cầu gửi cổng đã chọn lọc",
    "request_key": "Định danh chống tạo trùng yêu cầu đặt online", "request_type": "Loại yêu cầu phục vụ",
    "requested_at": "Thời điểm yêu cầu", "requested_by": "Tài khoản yêu cầu", "requested_snapshot": "Thông tin khách yêu cầu tại thời điểm gửi",
    "reservation": "Yêu cầu đặt online", "reservationpolicy": "Chính sách đặt online", "resolved": "Cờ đã xử lý yêu cầu",
    "response_data": "Dữ liệu phản hồi cổng đã chọn lọc", "review": "Trạng thái duyệt công", "reviewed_by": "Tài khoản xét duyệt",
    "rotated_at": "Thời điểm đổi token", "schedule": "Lịch làm việc", "sent_at": "Thời điểm gửi bếp",
    "served_at": "Thời điểm đã phục vụ", "session_data": "Dữ liệu phiên đã tuần tự hóa và ký xác thực",
    "session_digest": "Mã băm định danh phiên chấm công", "session_key": "Khóa phiên", "shift": "Ca làm",
    "shift_name": "Tên ca tại thời điểm phân lịch", "source_digest": "Mã băm thông tin nguồn yêu cầu",
    "staff_note": "Ghi chú nội bộ", "started_at": "Thời điểm bắt đầu chế biến", "starts_at": "Thời điểm bắt đầu",
    "state": "Trạng thái giữ nguyên liệu", "step": "Bước xác minh hiện tại", "stocktake": "Phiếu kiểm kê",
    "subtotal": "Tạm tính trước giảm giá", "supplier": "Nhà cung cấp", "table": "Bàn",
    "text": "Nội dung khách gửi", "thumbnail": "Đường dẫn/tên tệp ảnh thu nhỏ", "token": "Token truy cập",
    "token_hash": "Mã băm token thiết bị", "txn_ref": "Mã tham chiếu giao dịch", "unit_cost": "Giá vốn/đơn giá nguyên liệu tại thời điểm ghi nhận",
    "unit_name": "Tên đơn vị bán tại thời điểm ghi nhận", "unit_price": "Đơn giá bán tại thời điểm ghi nhận",
    "unit_price_snapshot": "Đơn giá bán tại thời điểm gửi yêu cầu", "used_at": "Thời điểm lượt xác minh đã sử dụng",
    "zp_trans_id": "Mã giao dịch ZaloPay", "cache_key": "Khóa bộ nhớ đệm", "value": "Giá trị",
    "expires": "Thời điểm hết hạn cache", "app": "Tên ứng dụng chứa migration", "applied": "Thời điểm áp dụng migration",
}

OVERRIDES = {
    ("accounts.User", "password"): "Chuỗi biểu diễn mật khẩu đã băm; không lưu mật khẩu rõ",
    ("accounts.User", "is_staff"): "Cờ cho phép truy cập Django Admin; không thay thế quyền quản lý nghiệp vụ",
    ("accounts.User", "is_superuser"): "Cờ tài khoản quản trị toàn hệ thống",
    ("admin.LogEntry", "action_flag"): "Mã thao tác quản trị: thêm, sửa hoặc xóa",
    ("admin.LogEntry", "change_message"): "Thông tin thay đổi được Django Admin ghi nhận",
    ("admin.LogEntry", "content_type"): "Loại đối tượng được thao tác trong Django Admin",
    ("admin.LogEntry", "object_repr"): "Chuỗi mô tả đối tượng tại thời điểm ghi nhật ký",
    ("auth.Permission", "codename"): "Mã quyền dùng khi kiểm tra phân quyền",
    ("auth.Permission", "content_type"): "Loại đối tượng áp dụng quyền",
    ("contenttypes.ContentType", "model"): "Tên model Django",
    ("workforce.WorkShift", "starts_at"): "Giờ bắt đầu ca trong ngày",
    ("workforce.WorkShift", "ends_at"): "Giờ kết thúc ca; có thể thuộc ngày kế tiếp theo kiểm tra ứng dụng",
    ("reservations.PreorderItem", "unit_cost"): "Giá vốn của dòng món đặt trước tại thời điểm trừ kho",
    ("orders.OnlinePayment", "deposit_amount"): "Số tiền cọc dự kiến khấu trừ khi xác nhận thanh toán",
    ("orders.Order", "split_root"): "Đơn gốc của nhóm tách thanh toán; NULL nếu là đơn gốc",
    ("inventory.InventoryTransaction", "order_item_reference"): "Mã dòng món liên quan; tham chiếu số ở ứng dụng, không phải khóa ngoại",
    ("inventory.InventoryTransaction", "source_id"): "Mã chứng từ nguồn theo source_type; không phải khóa ngoại",
    ("inventory.InventoryTransaction", "source_type"): "Loại chứng từ nguồn của biến động kho",
}


def serial(value):
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


def default_label(field):
    if getattr(field, "auto_now_add", False):
        return "ORM tự gán thời điểm khi tạo"
    if getattr(field, "auto_now", False):
        return "ORM tự gán thời điểm khi lưu trường này"
    if field.get_internal_type() in ("AutoField", "BigAutoField", "SmallAutoField"):
        return "PostgreSQL sinh tự tăng (identity/sequence)"
    if not field.has_default():
        return None
    value = field.default
    if value is list:
        return "[] (được tạo riêng cho mỗi bản ghi)"
    if value is dict:
        return "{} (được tạo riêng cho mỗi bản ghi)"
    if callable(value):
        return f"Hàm {value.__module__}.{value.__qualname__} (gọi khi tạo qua ORM)"
    return json.dumps(value, ensure_ascii=False, default=serial)


def validation_labels(field):
    labels = []
    for validator in field.validators:
        kind = type(validator).__name__
        limit = getattr(validator, "limit_value", None)
        if callable(limit):
            limit = "hàm tính giới hạn"
        if kind == "MinValueValidator":
            labels.append(f"Giá trị ≥ {limit}")
        elif kind == "MaxValueValidator":
            labels.append(f"Giá trị ≤ {limit}")
        elif kind == "MaxLengthValidator":
            labels.append(f"Độ dài ≤ {limit}")
        elif kind == "MinLengthValidator":
            labels.append(f"Độ dài ≥ {limit}")
        elif hasattr(validator, "regex"):
            labels.append("Mẫu hợp lệ: " + validator.regex.pattern)
        elif kind == "EmailValidator":
            labels.append("Định dạng email hợp lệ")
        elif kind == "DecimalValidator":
            continue  # precision/scale already appear in the SQL type
        else:
            labels.append(kind)
    return list(dict.fromkeys(labels))


def field_description(model, field):
    name = field.name
    override = OVERRIDES.get((model._meta.label, name))
    if override:
        return override
    label = str(field.verbose_name)
    # Retain explicitly authored Vietnamese labels; translate autogenerated English.
    if not label.isascii():
        return label[:1].upper() + label[1:]
    return LABELS.get(name, label[:1].upper() + label[1:])


def read_schema():
    models = {m._meta.db_table: m for m in apps.get_models(include_auto_created=True)}
    fields_by_table = defaultdict(list)
    constraints_by_table = defaultdict(list)
    indexes_by_table = defaultdict(list)
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
            cursor.execute("""
                SELECT c.relname, a.attnum, a.attname, format_type(a.atttypid, a.atttypmod),
                       a.attnotnull, pg_get_expr(d.adbin, d.adrelid), a.attidentity
                FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                JOIN pg_attribute a ON a.attrelid=c.oid
                LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum
                WHERE n.nspname=current_schema() AND c.relkind IN ('r','p')
                  AND a.attnum>0 AND NOT a.attisdropped
                ORDER BY c.relname,a.attnum
            """)
            for table, ordinal, name, sql_type, not_null, db_default, identity in cursor.fetchall():
                fields_by_table[table].append({"ordinal": ordinal, "name": name,
                    "type": sql_type, "nullable": not not_null, "db_default": db_default,
                    "identity": identity or None})
            cursor.execute("""
                SELECT c.relname, con.conname, con.contype, pg_get_constraintdef(con.oid,true),
                       ARRAY(SELECT a.attname FROM unnest(con.conkey) WITH ORDINALITY AS k(num,ord)
                             JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum=k.num ORDER BY k.ord)
                FROM pg_constraint con JOIN pg_class c ON c.oid=con.conrelid
                JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname=current_schema() ORDER BY c.relname,con.conname
            """)
            for table, name, kind, definition, columns in cursor.fetchall():
                constraints_by_table[table].append({"name": name, "kind": kind,
                    "definition": definition, "columns": columns})
            cursor.execute("""
                SELECT t.relname,i.relname,pg_get_indexdef(i.oid)
                FROM pg_index ix JOIN pg_class t ON t.oid=ix.indrelid
                JOIN pg_class i ON i.oid=ix.indexrelid JOIN pg_namespace n ON n.oid=t.relnamespace
                WHERE n.nspname=current_schema() ORDER BY t.relname,i.relname
            """)
            for table, name, definition in cursor.fetchall():
                indexes_by_table[table].append({"name": name, "definition": definition})
        executor = MigrationExecutor(connection)
        pending = [(m.app_label, m.name) for m, _ in executor.migration_plan(executor.loader.graph.leaf_nodes())]

    tables = []
    mismatches = []
    for table_name, db_fields in fields_by_table.items():
        model = models.get(table_name)
        label = model._meta.label if model else table_name
        if label not in DESCRIPTIONS:
            raise ValueError(f"Missing table description: {label}")
        title, purpose = DESCRIPTIONS[label]
        model_fields = {f.column: f for f in model._meta.local_fields} if model else {}
        if model and set(model_fields) != {f["name"] for f in db_fields}:
            mismatches.append(table_name + ": danh sách cột model và PostgreSQL khác nhau")
        for field in db_fields:
            mf = model_fields.get(field["name"])
            field.update({"description": LABELS.get(field["name"], field["name"]), "model_default": None,
                "blank": None, "choices": [], "validators": [], "reference": None})
            if mf:
                field.update({"description": field_description(model, mf), "model_default": default_label(mf),
                    "blank": mf.blank, "choices": [[str(k), str(v)] for k, v in mf.flatchoices],
                    "validators": validation_labels(mf), "help_text": str(mf.help_text) if mf.help_text else "",
                    "model_type": mf.get_internal_type()})
                if mf.null != field["nullable"]:
                    mismatches.append(f"{table_name}.{field['name']}: NULL model và PostgreSQL khác nhau")
                if mf.is_relation and (mf.many_to_one or mf.one_to_one):
                    field["reference"] = {"table": mf.related_model._meta.db_table,
                        "column": mf.target_field.column, "orm_on_delete": mf.remote_field.on_delete.__name__,
                        "one_to_one": mf.one_to_one}
            constraints = constraints_by_table[table_name]
            keys = []
            if any(c["kind"] == "p" and field["name"] in c["columns"] for c in constraints):
                keys.append("PK")
            if field["reference"] or any(c["kind"] == "f" and field["name"] in c["columns"] for c in constraints):
                keys.append("FK")
            if any(c["kind"] == "u" and c["columns"] == [field["name"]] for c in constraints):
                keys.append("UQ")
            field["keys"] = keys
        app = model._meta.app_label if model else "technical"
        group = app if app in {name for name, _ in GROUPS[:-1]} else "technical"
        tables.append({"name": table_name, "model": label if model else None, "title": title,
            "purpose": purpose, "group": group, "columns": db_fields,
            "constraints": constraints_by_table[table_name], "indexes": indexes_by_table[table_name]})
    if mismatches or pending:
        raise ValueError(json.dumps({"mismatches": mismatches, "pending_migrations": pending}, ensure_ascii=False))
    for table_name in models:
        if table_name not in fields_by_table:
            raise ValueError(f"Model table missing from PostgreSQL: {table_name}")
    return {"generated_on": timezone.localdate().isoformat(), "vendor": connection.vendor,
        "postgresql_version_num": connection.pg_version, "table_count": len(tables),
        "column_count": sum(len(t["columns"]) for t in tables),
        "foreign_key_count": sum(c["kind"] == "f" for t in tables for c in t["constraints"]),
        "model_table_count": len(models), "model_column_nullable_match": True,
        "pending_migrations": pending, "tables": tables}


class Document:
    def __init__(self):
        self.md = []
        self.html = []

    @staticmethod
    def rich(text):
        return re.sub(r"`([^`]+)`", r"<code>\1</code>", escape(str(text)))

    def heading(self, level, title, anchor=None):
        self.md.extend(["#" * level + " " + title, ""])
        attr = f' id="{escape(anchor)}"' if anchor else ""
        self.html.append(f"<h{level}{attr}>{escape(title)}</h{level}>")

    def paragraph(self, text):
        self.md.extend([text, ""])
        self.html.append("<p>" + self.rich(text) + "</p>")

    def bullets(self, items):
        self.md.extend(["- " + item for item in items] + [""])
        self.html.append("<ul>" + "".join("<li>" + self.rich(item) + "</li>" for item in items) + "</ul>")

    def table(self, headers, rows):
        def cell(text):
            return str(text).replace("|", "\\|").replace("\n", " ")
        self.md.append("| " + " | ".join(map(cell, headers)) + " |")
        self.md.append("| " + " | ".join("---" for _ in headers) + " |")
        self.md.extend("| " + " | ".join(map(cell, row)) + " |" for row in rows)
        self.md.append("")
        head = "".join("<th scope=\"col\">" + self.rich(x) + "</th>" for x in headers)
        body = "".join("<tr>" + "".join("<td>" + self.rich(x) + "</td>" for x in row) + "</tr>" for row in rows)
        self.html.append('<div class="table-wrap"><table><thead><tr>' + head + "</tr></thead><tbody>" + body + "</tbody></table></div>")


def author(schema):
    doc = Document()
    doc.heading(1, "ĐẶC TẢ CƠ SỞ DỮ LIỆU HỆ THỐNG QUẢN LÝ NHÀ HÀNG CƠM QUÊ", "top")
    doc.paragraph("Phiên bản ngày " + schema["generated_on"] + ". Hệ quản trị PostgreSQL; ứng dụng Django.")
    doc.heading(2, "1. Tổng quan và quy ước", "overview")
    doc.paragraph(f"Cơ sở dữ liệu gồm {schema['table_count']} bảng, {schema['column_count']} cột và {schema['foreign_key_count']} khóa ngoại vật lý. "
        f"Trong đó {schema['model_table_count']} bảng được khai báo qua model Django, hai bảng còn lại là lịch sử migration và cache chatbot. "
        "Các phân hệ báo cáo, cổng khách hàng và AI có thể dùng dữ liệu từ những bảng này mà không có bảng riêng cho từng màn hình.")
    doc.bullets([
        "Tên bảng và tên cột bên dưới là tên vật lý đang sử dụng. Cột khóa ngoại theo quy ước Django thường kết thúc bằng `_id`.",
        "PK: khóa chính; FK: khóa ngoại; UQ: duy nhất một cột. Duy nhất ghép, theo biểu thức hoặc có điều kiện được ghi ở phần ràng buộc/chỉ mục.",
        "NULL = Có: database cho phép NULL; NULL = Không: NOT NULL. Trường văn bản có thể cho chuỗi rỗng dù không cho NULL; không đồng nhất hai trường hợp.",
        "Giá trị mặc định ORM được ứng dụng Django gán; chỉ giá trị ghi tại mục mặc định PostgreSQL mới là default phía database. Không gọi hàm tạo token để lấy giá trị ví dụ.",
        "Danh sách lựa chọn (`choices`) và validator là quy tắc model. Chúng chỉ được bảo đảm bởi PostgreSQL khi có CHECK/UNIQUE/kiểu dữ liệu tương ứng bên dưới; gọi `save()` không tự chạy mọi kiểm tra `full_clean()`.",
        "PROTECT, CASCADE và SET_NULL ở bảng quan hệ là chính sách xóa của Django ORM. Không diễn giải chúng thành ON DELETE CASCADE trong SQL; định nghĩa FK thực tế được lưu trong bản metadata đi kèm.",
        "Các cột timestamp with time zone lưu thời điểm; ứng dụng hiển thị theo Asia/Ho_Chi_Minh. time without time zone dùng cho giờ ca và cấu hình giờ mở cửa.",
        "Tiền được lưu bằng numeric/Decimal, không dùng số thực nhị phân. numeric(p,s) có tổng p chữ số, trong đó s chữ số thập phân. Số lượng nguyên liệu thường có 3 chữ số thập phân.",
        "Các khóa identity/sequence có thể có khoảng trống, không phải số đếm liên tục hoặc số thứ tự chứng từ pháp lý.",
    ])
    doc.table(["Kiểu PostgreSQL", "Diễn giải"], [
        ["bigint / integer / smallint", "Số nguyên; miền không âm của các Positive*Field phải xem CHECK thực tế."],
        ["character varying(n)", "Chuỗi tối đa n ký tự."], ["text", "Văn bản có độ dài thay đổi; giới hạn form/model có thể được mô tả riêng."],
        ["numeric(p,s)", "Số thập phân chính xác cho tiền, giá vốn và số lượng."], ["boolean", "Cờ đúng/sai."],
        ["timestamp with time zone", "Ngày giờ có ngữ nghĩa múi giờ."], ["date / time without time zone", "Ngày hoặc giờ trong ngày."],
        ["uuid", "Định danh UUID."], ["jsonb", "Dữ liệu cấu trúc JSON; không phải khóa ngoại."],
        ["double precision", "Số thực dùng cho góc tư thế nhận diện; không dùng để lưu tiền."],
    ])

    doc.heading(2, "2. Danh mục bảng", "catalog")
    rows = []
    numbered = []
    table_number = 0
    for group, group_title in GROUPS:
        rank = {label: index for index, label in enumerate(DESCRIPTIONS)}
        group_tables = sorted([t for t in schema["tables"] if t["group"] == group],
            key=lambda t: rank.get(t["model"] or t["name"], len(rank)))
        for table in group_tables:
            table_number += 1
            table["number"] = table_number
            numbered.append(table)
            rows.append([table_number, group_title, "`" + table["name"] + "`", table["title"], len(table["columns"])])
    doc.table(["STT", "Phân hệ", "Tên bảng", "Ý nghĩa", "Số cột"], rows)

    doc.heading(2, "3. Các quan hệ nghiệp vụ chính", "relationships")
    doc.paragraph("Bội số dưới đây đọc từ bảng cha sang bảng con. FK NOT NULL bảo đảm mỗi bản ghi con có một cha; không tự bảo đảm cha phải có ít nhất một con.")
    doc.table(["Bảng cha / thực thể", "Bảng con / liên kết", "Quan hệ", "Diễn giải"], [
        ["Tài khoản", "Hồ sơ nhân viên", "1 — 0..1", "Mỗi hồ sơ có đúng một tài khoản; tài khoản có thể chưa có hồ sơ."],
        ["Nhóm quyền", "Chức vụ", "1 — 0..1", "Mỗi chức vụ thuộc đúng một nhóm; group_id duy nhất trong chức vụ."],
        ["Khu vực", "Bàn", "1 — 0..N", "Mỗi bàn thuộc một khu vực."],
        ["Khách hàng", "Lịch đặt/lượt khách", "0..1 — 0..N", "Khách trực tiếp có thể không gắn hồ sơ; CHECK yêu cầu khách cho lịch không phải walk-in."],
        ["Bàn", "Lịch đặt/lượt khách", "1 — 0..N", "Nhiều lịch theo thời gian; chống trùng thời gian được xử lý trong service có khóa giao dịch."],
        ["Lịch đặt/lượt khách", "Đơn hàng", "0..1 — 0..1", "booking_id của đơn là FK duy nhất, cho NULL; mỗi lượt tối đa một đơn trực tiếp."],
        ["Lịch đặt/lượt khách", "Yêu cầu đặt online", "0..1 — 0..1", "booking_id của yêu cầu online là FK duy nhất, cho NULL."],
        ["Đơn gốc", "Đơn con khi tách", "0..1 — 0..N", "Đơn con dùng split_root_id; đơn gốc không bắt buộc có đơn con."],
        ["Đơn hàng", "Chi tiết đơn", "1 — 0..N tại schema", "Mỗi dòng thuộc một đơn; điều kiện có món phụ thuộc bước xử lý của ứng dụng."],
        ["Đơn hàng", "Hóa đơn", "1 — 0..1", "Invoice.order_id duy nhất và NOT NULL; hóa đơn chưa có khi đơn mới mở."],
        ["Hóa đơn", "Phiếu thu", "1 — 0..N", "Mỗi phiếu thu thuộc một hóa đơn. Schema nhiều phiếu không đồng nghĩa giao diện hỗ trợ chia tùy ý từng lần thu."],
        ["Yêu cầu đặt online", "Món đặt trước / trả cọc / hoàn cọc", "1 — 0..N", "Các bảng chi tiết lưu lịch sử theo yêu cầu online."],
        ["Hóa đơn", "Khấu trừ cọc", "1 — 0..1", "Mỗi hóa đơn tối đa một dòng phân bổ cọc; một yêu cầu online có thể có nhiều phân bổ."],
        ["Danh mục món", "Món ăn", "1 — 0..N", "Mỗi món thuộc một danh mục và một đơn vị bán."],
        ["Món ăn", "Nguyên liệu", "N — N qua RecipeIngredient", "Định mức lưu lượng nguyên liệu cho một đơn vị món; cặp món–nguyên liệu duy nhất."],
        ["Combo", "Món ăn", "N — N qua ComboItem", "Có số lượng theo thành phần combo."],
        ["Nhà cung cấp", "Phiếu nhập", "1 — 0..N", "Phiếu nhập hàng bắt buộc có nhà cung cấp."],
        ["Phiếu nhập / Phiếu kiểm kê", "Chi tiết tương ứng", "1 — 0..N tại schema", "Quy tắc chốt phiếu có chi tiết do ứng dụng kiểm tra."],
        ["Nhân viên", "Lịch làm việc", "1 — 0..N", "Một lịch thuộc một nhân viên và một ca."],
        ["Lịch làm việc", "Bản ghi chấm công", "1 — 0..1", "schedule_id của Attendance là FK duy nhất và NOT NULL."],
        ["Nhân viên", "Mẫu khuôn mặt", "1 — 0..1", "Mỗi nhân viên tối đa một hồ sơ mẫu nhận diện."],
    ])
    doc.paragraph("Phiên bản đang triển khai không có bảng ChiTietHoaDon/InvoiceItem. Tách thanh toán được biểu diễn bằng Order.split_root và các dòng món thuộc đơn con. Không thêm quan hệ phân bổ món vào nhiều hóa đơn vào đặc tả vật lý khi chưa có bảng tương ứng.")

    doc.heading(2, "4. Quy tắc toàn vẹn và dữ liệu lịch sử", "integrity")
    doc.table(["Nhóm quy tắc", "Cách thể hiện"], [
        ["Toàn vẹn thực thể", "PK và identity/UUID; UNIQUE bảo vệ mã nghiệp vụ và quan hệ một–một."],
        ["Toàn vẹn tham chiếu", "FK PostgreSQL; nhiều FK được khai báo DEFERRABLE INITIALLY DEFERRED. Chính sách xóa nghiệp vụ được Django ORM xử lý."],
        ["Miền giá trị", "Kiểu dữ liệu, NOT NULL, CHECK, UNIQUE/index. Choices/validator riêng được ghi rõ ở từng bảng."],
        ["Cập nhật đồng thời", "Các cột revision/session_version hỗ trợ phát hiện dữ liệu cũ. Service còn dùng transaction, khóa hàng và advisory lock; không phải chỉ có cột revision là database tự chống xung đột."],
        ["Bảo toàn lịch sử", "Snapshot tên, đơn giá, giá vốn, khuyến mãi và người thao tác giúp giữ ý nghĩa chứng từ khi danh mục thay đổi."],
        ["Số tiền tổng hợp", "Một số tổng được lưu để chốt chứng từ hoặc tối ưu đọc; phải được service cập nhật trong cùng transaction. Không khẳng định mô hình hoàn toàn không có dữ liệu lặp."],
        ["Trạng thái nghiệp vụ", "Các mã trạng thái cho biết miền lựa chọn; chuyển trạng thái hợp lệ, quyền thao tác và việc xác nhận từ cổng thanh toán được service kiểm tra."],
        ["Đặt bàn và kho giữ chỗ", "Kiểm tra trùng thời gian, sức chứa, đủ nguyên liệu khả dụng và khấu trừ cọc cần phối hợp nhiều bảng; không suy ra tất cả từ một CHECK."],
        ["Thông tin nhạy cảm", "Mật khẩu lưu dạng băm; thiết bị lưu token_hash. Token truy cập riêng và vector khuôn mặt là dữ liệu cần kiểm soát truy cập, không đưa giá trị thật vào báo cáo."],
    ])

    doc.heading(2, "5. Đặc tả chi tiết các bảng", "details")
    for group_no, (group, group_title) in enumerate(GROUPS, 1):
        group_tables = [t for t in numbered if t["group"] == group]
        doc.heading(3, f"5.{group_no}. {group_title}", f"group-{group}")
        for local_no, table in enumerate(group_tables, 1):
            table_id = "table-" + table["name"]
            doc.html.append(f'<section class="table-section" id="{table_id}" data-search="{escape(table["name"] + " " + table["title"])}">')
            doc.heading(4, f"5.{group_no}.{local_no}. {table['title']} — {table['name']}")
            doc.paragraph("Chức năng: " + table["purpose"])
            if table["model"]:
                doc.paragraph("Model: `" + table["model"] + "`.")
            else:
                doc.paragraph("Bảng kỹ thuật không được đăng ký thành model nghiệp vụ trong ứng dụng.")
            doc.table(["STT", "Tên trường", "Kiểu PostgreSQL", "Khóa", "NULL", "Diễn giải"], [
                [f["ordinal"], "`" + f["name"] + "`", "`" + f["type"] + "`", ", ".join(f["keys"]) or "—",
                 "Có" if f["nullable"] else "Không", f["description"]] for f in table["columns"]
            ])
            references = [f for f in table["columns"] if f["reference"]]
            if references:
                doc.paragraph("Khóa ngoại và chính sách liên kết:")
                doc.table(["Trường", "Tham chiếu", "Một bản ghi hiện tại liên kết", "Khi xóa qua ORM"], [
                    ["`" + f["name"] + "`", "`" + f["reference"]["table"] + "." + f["reference"]["column"] + "`",
                     ("0 hoặc 1" if f["nullable"] else "Đúng 1") + ("; FK duy nhất" if f["reference"]["one_to_one"] else ""),
                     f["reference"]["orm_on_delete"]] for f in references
                ])
            rules = []
            for f in table["columns"]:
                parts = []
                if f["model_default"] is not None:
                    parts.append("Mặc định ORM: " + f["model_default"])
                if f["identity"]:
                    parts.append("PostgreSQL identity: " + ("GENERATED BY DEFAULT" if f["identity"] == "d" else "GENERATED ALWAYS"))
                if f["db_default"] is not None:
                    parts.append("Mặc định PostgreSQL: " + f["db_default"])
                if f["choices"]:
                    parts.append("Lựa chọn model: " + "; ".join(f"`{k}` = {v}" for k, v in f["choices"]))
                if f["validators"]:
                    parts.append("Kiểm tra model: " + "; ".join(f["validators"]))
                if f["blank"] is True and ("character varying" in f["type"] or f["type"] == "text"):
                    parts.append("Form/model cho phép để trống")
                if parts:
                    rules.append(["`" + f["name"] + "`", ". ".join(parts)])
            if rules:
                doc.paragraph("Giá trị mặc định và quy tắc model (phân biệt với ràng buộc database):")
                doc.table(["Trường", "Quy tắc"], rules)
            actual_constraints = [c for c in table["constraints"] if c["kind"] in ("p", "u", "c", "x")]
            if actual_constraints:
                doc.paragraph("Ràng buộc vật lý đang có trong PostgreSQL:")
                doc.table(["Tên", "Loại", "Định nghĩa"], [
                    ["`" + c["name"] + "`", {"p": "PRIMARY KEY", "u": "UNIQUE", "c": "CHECK", "x": "EXCLUDE"}[c["kind"]],
                     "`" + c["definition"] + "`"] for c in actual_constraints
                ])
            constraint_names = {c["name"] for c in table["constraints"]}
            indexes = [i for i in table["indexes"] if i["name"] not in constraint_names]
            if indexes:
                doc.html.append('<details class="indexes"><summary>Chỉ mục bổ sung (' + str(len(indexes)) + ")</summary>")
                doc.paragraph("Chỉ mục bổ sung (không lặp lại chỉ mục phục vụ PK/UNIQUE phía trên):")
                doc.table(["Tên chỉ mục", "Định nghĩa PostgreSQL"], [["`" + i["name"] + "`", "`" + i["definition"] + "`"] for i in indexes])
                doc.html.append("</details>")
            doc.html.append("</section>")

    doc.heading(2, "6. Các điểm cần phân biệt khi sử dụng đặc tả", "notes")
    doc.bullets([
        "Không có một bảng PhieuKho tổng quát như sơ đồ lớp rút gọn: nhập hàng dùng PurchaseReceipt/PurchaseReceiptLine, kiểm kê dùng Stocktake/StocktakeLine, hao hụt dùng WasteRecord; sổ biến động là InventoryTransaction.",
        "InventoryTransaction.order_item_reference, source_type/source_id và các nhật ký object_id không tự trở thành FK. Không vẽ liên kết vật lý do database bảo đảm cho các cột này.",
        "PromotionCode được chốt vào Order/Invoice bằng chuỗi snapshot mã khuyến mãi; không có FK trực tiếp từ các cột snapshot đó đến bảng chương trình.",
        "customer_code, booking_code, một số subtotal/difference, số phút công và các property Python không mặc nhiên là cột lưu trữ. Chỉ cột trong bảng đặc tả mới được tính vào schema vật lý.",
        "Quan hệ dữ liệu một–nhiều không buộc chứng từ cha có ít nhất một dòng khi mới tạo. Quy trình nháp/xác nhận của ứng dụng có thể yêu cầu điều kiện bổ sung.",
        "Báo cáo chủ yếu tổng hợp các bảng nghiệp vụ. Model Apriori và kết quả dự báo hiện còn lưu theo file; không bổ sung bảng AIModel/ForecastResult khi code chưa khai báo.",
        "Các cột ImageField lưu tên/đường dẫn tài nguyên, không lưu trực tiếp toàn bộ ảnh dưới dạng nhị phân trong PostgreSQL.",
        "Không dùng đặc tả này để chạy DDL thay cho migration. Thay đổi schema phải đi qua migration và kiểm thử các luồng liên quan.",
    ])
    doc.heading(2, "7. Nguồn và xác minh", "verification")
    doc.paragraph("Tên bảng/cột, kiểu dữ liệu, NULL, identity, default PostgreSQL, constraint và index được đọc từ catalog của database đang cấu hình bằng giao dịch READ ONLY. Mô tả nghiệp vụ, lựa chọn, validator, mặc định ORM và chính sách xóa được đối chiếu model trong mã nguồn hiện tại. Không truy xuất nội dung hồ sơ, mật khẩu, hóa đơn, giao dịch hay vector nhận diện để sinh tài liệu.")
    doc.paragraph(f"Kết quả đối chiếu: đủ {schema['model_table_count']} bảng model; danh sách cột và NULL khớp PostgreSQL; không có migration chờ áp dụng. Đối chiếu này không khẳng định đã kiểm thử từng quy tắc service hoặc cấu hình của một máy chủ production khác.")
    doc.paragraph("Tạo lại bằng: `.venv/Scripts/python.exe -X utf8 scripts/generate_database_spec.py`. Nguồn metadata: `database-specification/schema-current.json`.")
    return doc, numbered


CSS = """
:root{--ink:#18212c;--muted:#526170;--accent:#185c50;--line:#d9e1e5;--bg:#f2f5f6}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.65 'Segoe UI',Arial,sans-serif}
aside{position:fixed;inset:0 auto 0 0;width:285px;background:#fff;border-right:1px solid var(--line);padding:24px 18px;overflow:auto}
aside strong{font-size:18px;display:block;margin-bottom:12px}aside small{display:block;margin-bottom:12px}aside label{display:block;font-size:13px}aside a{display:block;color:var(--ink);text-decoration:none;font-size:13px;padding:5px 8px;border-radius:5px}aside a:hover{background:#e9f2ef;color:var(--accent)}
.group-label{margin:15px 6px 4px;font-weight:650;color:var(--accent);font-size:13px}input{width:100%;padding:10px;border:1px solid #b7c5cc;border-radius:6px;font:inherit;margin:8px 0}
main{margin-left:285px;padding:36px clamp(24px,4vw,68px) 80px;max-width:1700px}h1{font-size:30px;line-height:1.3;max-width:950px;margin:0 0 16px;text-wrap:balance}h2{font-size:24px;margin:44px 0 16px}h3{font-size:20px;margin:36px 0 14px}h4{font-size:18px;line-height:1.5;margin:0 0 12px;overflow-wrap:anywhere}
p{margin:12px 0}li{margin-bottom:6px}.table-section{background:#fff;border:1px solid var(--line);border-top:4px solid var(--accent);border-radius:8px;margin:24px 0;padding:24px;scroll-margin-top:20px}
.table-wrap{width:100%;overflow-x:auto;margin:14px 0 22px}table{border-collapse:collapse;width:100%;font-size:13px;text-align:left}th,td{border:1px solid var(--line);padding:9px 10px;vertical-align:top;overflow-wrap:anywhere}th{background:#eaf1ee;color:#173d35;font-weight:650}tbody tr:nth-child(even){background:#fafcfc}code{font:12px/1.6 Consolas,'Courier New',monospace;overflow-wrap:anywhere;color:#173d35}table code{font-size:12px}details{margin-top:18px}summary{cursor:pointer;color:var(--accent);font-weight:650}button{background:var(--accent);color:#fff;border:0;border-radius:6px;padding:9px 14px;cursor:pointer;font:inherit}small{color:var(--muted)}.hidden{display:none!important}
@media(max-width:1000px){aside{position:static;width:auto;max-height:320px;border-bottom:1px solid var(--line)}main{margin:0;padding:24px 16px}.table-section{padding:16px}h1{font-size:24px}}
@media print{body{background:#fff;font:10pt/1.45 Arial,sans-serif}aside{display:none}main{margin:0;padding:0;max-width:none}h1{font-size:19pt}h2{font-size:15pt}h3{font-size:13pt}h4{font-size:11pt;break-after:avoid}.table-section{border:0;border-radius:0;padding:0;margin:20pt 0}table{font-size:8pt}th,td{padding:5pt}tr{break-inside:avoid}thead{display:table-header-group}.table-wrap{overflow:visible}code,table code{font-size:7.5pt}.hidden{display:block!important}details>*{display:block}summary{display:none}@page{size:A4 landscape;margin:15mm}}
"""


def main():
    schema = read_schema()
    doc, numbered = author(schema)
    metadata_dir = OUTPUT / "database-specification"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    (metadata_dir / "schema-current.json").write_text(json.dumps(schema, ensure_ascii=False, indent=2, default=serial) + "\n", encoding="utf-8")
    (OUTPUT / "dac-ta-co-so-du-lieu.md").write_text("\n".join(doc.md), encoding="utf-8")
    nav = ['<strong>CƠM QUÊ · Đặc tả CSDL</strong><small>' + str(schema["table_count"]) + ' bảng · ' + str(schema["column_count"]) + ' cột</small>',
        '<label for="filter">Tìm bảng hoặc nội dung</label><input id="filter" type="search" placeholder="Ví dụ: hóa đơn, orders_invoice…">',
        '<button type="button" id="print">In / Lưu PDF</button><a href="#overview">Tổng quan và quy ước</a><a href="#catalog">Danh mục bảng</a><a href="#relationships">Các quan hệ chính</a><a href="#integrity">Quy tắc toàn vẹn</a>']
    for group, title in GROUPS:
        nav.append('<div class="group-label">' + escape(title) + '</div>')
        for table in numbered:
            if table["group"] == group:
                nav.append(f'<a class="table-link" href="#table-{table["name"]}">{table["number"]}. {escape(table["title"])}</a>')
    nav.append('<a href="#notes">Lưu ý sử dụng</a><a href="#verification">Nguồn và xác minh</a>')
    script = """
const input=document.getElementById('filter');
const norm=value=>value.toLowerCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g,'').replace(/đ/g,'d');
input.addEventListener('input',()=>{const q=norm(input.value.trim());document.querySelectorAll('.table-section').forEach(section=>{const hide=!!q&&!norm(section.textContent).includes(q);section.classList.toggle('hidden',hide);const link=document.querySelector('a[href="#'+section.id+'"]');if(link)link.classList.toggle('hidden',hide);});});
document.getElementById('print').addEventListener('click',()=>{document.querySelectorAll('details').forEach(d=>d.open=true);window.print();});
"""
    page = '<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Đặc tả cơ sở dữ liệu Cơm Quê</title><style>' + CSS + '</style></head><body><aside>' + "".join(nav) + '</aside><main>' + "\n".join(doc.html) + '</main><script>' + script + '</script></body></html>'
    (OUTPUT / "dac-ta-co-so-du-lieu.html").write_text(page, encoding="utf-8")
    print(json.dumps({"tables": schema["table_count"], "columns": schema["column_count"],
        "foreign_keys": schema["foreign_key_count"], "model_tables": schema["model_table_count"],
        "by_group": dict(Counter(t["group"] for t in schema["tables"])),
        "outputs": ["docs/dac-ta-co-so-du-lieu.md", "docs/dac-ta-co-so-du-lieu.html", "docs/database-specification/schema-current.json"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
