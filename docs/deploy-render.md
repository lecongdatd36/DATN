# Đưa bản hiện tại lên Render

Repo dùng nhánh chính `master`. Bản phát hành gồm đặt bàn online, món đặt trước, cọc, ZaloPay Sandbox và ca làm/chấm công. Mã nguồn, migration, template và static phải cùng phiên bản. Không đưa `.env`, database local, ảnh người dùng, mẫu khuôn mặt, file Word cá nhân hoặc artifact kiểm thử lên Git.

## Cấu hình service hiện có

Trong Render Dashboard, mở **Web Service đang chạy**:

| Mục | Giá trị |
| --- | --- |
| Repository | `lecongdatd36/DATN` |
| Branch | `master` |
| Runtime | Python |
| Build Command | `bash build.sh` |
| Start Command | `python -m gunicorn QLNH.wsgi:application --bind 0.0.0.0:$PORT` |
| Python | `.python-version` chọn nhánh 3.12; nếu service có `PYTHON_VERSION` thì biến đó được ưu tiên, cần dùng bản 3.12.x phù hợp |

Giữ Start Command hiện có nếu đang chạy Gunicorn hợp lệ. Auto-Deploy phải theo nhánh `master`; nếu tắt thì dùng **Manual Deploy → Deploy latest commit** sau khi push. Đối chiếu commit trong log Render và đợi service Live trước khi kết luận deploy thành công.

Nguồn: [Render Django](https://render.com/docs/deploy-django), [Auto-Deploy](https://render.com/docs/deploys), [Python version](https://render.com/docs/python-version).

## Biến môi trường

Đặt giá trị thật trong **Environment** của Render. `.env.example` chỉ là mẫu, không tự đồng bộ biến từ máy local lên Render.

| Biến | Cách cấu hình |
| --- | --- |
| `SECRET_KEY` | Giữ khóa bí mật ổn định của môi trường đang chạy |
| `DATABASE_URL` | Kết nối PostgreSQL của môi trường Render, kiểm tra đúng database trước migration |
| `DEBUG` | `False` |
| `ALLOWED_HOSTS` | Hostname website, không có `https://`; hostname Render được code tự thêm |
| `CSRF_TRUSTED_ORIGINS` | Origin HTTPS website; thêm custom domain nếu có, phân cách bằng dấu phẩy |
| `PUBLIC_BASE_URL` | URL HTTPS website; để trống dùng `RENDER_EXTERNAL_URL` của Render; không dùng localhost hoặc IP LAN |
| `CLOUDINARY_URL` | Cấu hình Cloudinary cho ảnh tải lên; hoặc giữ bộ `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET` hiện có |
| `ZALOPAY_APP_ID`, `ZALOPAY_KEY1`, `ZALOPAY_KEY2` | Bộ thông tin **Sandbox** của cùng một ứng dụng |
| `ZALOPAY_ENDPOINT` | `https://sb-openapi.zalopay.vn/v2/create` |
| `ZALOPAY_CALLBACK_URL` | `https://<hostname-website>/payments/zalopay/callback/`; để trống dùng origin request, URL phải truy cập được từ ZaloPay |
| `ENABLE_FACE_ATTENDANCE` | `0` nếu chưa bật nhận diện; `1` để build cài requirements-attendance và tải mô hình đã kiểm checksum |

Giữ cấu hình VNPAY, chatbot, dự báo và thông tin nhà hàng hiện có nếu dùng. Thanh toán ZaloPay vẫn là Sandbox. Callback/Query đã xác thực mới xác nhận thu tiền; redirect chỉ đưa khách về màn trạng thái.

Nguồn: [Render Environment](https://render.com/docs/configure-environment-variables). Chi tiết thanh toán trong [ZaloPay Sandbox](zalopay-sandbox.md).

## Database và dữ liệu

Sao lưu database hosting theo quy trình đang dùng trước đợt migration. `build.sh` thực hiện cài `requirements.txt`, cài bộ nhận diện nếu bật, rồi chạy:

```sh
python scripts/compile_translations.py
python manage.py collectstatic --no-input
python manage.py migrate
python manage.py createcachetable qlnh_chatbot_cache
```

Các migration mới: `orders/0021`, `orders/0022`, `reservations/0001`–`0004`, `workforce/0001`–`0002`. Chúng bổ sung schema; các đơn đặt/cọc ở máy local không tự chuyển lên hosting. Không chạy `flush`, nạp fixture mẫu hoặc reset database để deploy.

Nhánh giao diện/giỏ/combo bổ sung `menu/0006` và `reservations/0005`, font cùng asset banner trong `static/customer/`. Chạy migrate/collectstatic theo `build.sh` khi triển khai nhánh này. Combo là dữ liệu riêng từng môi trường: quản lý tạo tại `/thuc-don/combo/` hoặc chạy `python manage.py seed_combos --actor <username-quan-ly>` để thêm ba combo khởi tạo nếu thực đơn có đủ món; lệnh giữ nguyên mã combo đã tồn tại. Xem [giỏ và combo](homepage-refresh.md).

Chấm công một nút tự xác định vào/ra bổ sung migration `workforce/0003`; `migrate` giữ nguyên công và mẫu khuôn mặt cũ. Trang chấm công chung dùng bố cục camera / kết quả mới, bỏ GPS, chặn chấm lặp 60 giây. Dashboard quản lý `/tai-khoan/` và theme dùng static mới, không thêm biến môi trường. Xem [chấm công](attendance-kiosk.md) và [dashboard](management-dashboard.md).

Tiếng Anh bổ sung `menu/0007`, nút VI / EN và catalog `locale/en/LC_MESSAGES/`. Build tự biên dịch `.po` thành `.mo`; không cần biến môi trường mới. Sau migrate, quản lý điền tên/giới thiệu tiếng Anh trong catalog hoặc chạy `python manage.py seed_menu_english` để điền những ô còn trống của các món/combo đã biết. Lệnh giữ nguyên bản dịch tùy chỉnh, tên Việt, giá và dữ liệu giao dịch. Kiểm tra chuyển VI / EN ở trang chủ, `/menu/`, giỏ món và form đặt bàn sau deploy.

Ảnh trong `media/` local và dữ liệu đăng ký khuôn mặt không đi theo Git. Dùng dữ liệu/Cloudinary của đúng môi trường. Sau deploy, quản lý kiểm tra chính sách cọc, món được phép chuẩn bị trước, ca làm và cấu hình điểm chấm công; các cấu hình này lưu trong database của từng môi trường.

Nếu bật nhận diện, inference chạy trên server Render và cần đủ RAM/CPU. Chạy thử với tài khoản/điểm chấm công của môi trường kiểm thử trước; việc cài mô hình không tự đăng ký khuôn mặt nhân viên. Xem [chấm công](attendance-kiosk.md).

## Tác vụ định kỳ

Các lệnh sau cần chạy trên cùng database và cùng cấu hình với web service:

```sh
python manage.py expire_reservation_holds
python manage.py query_pending_zalopay
```

Có thể cấu hình scheduler mỗi phút để giải phóng giữ chỗ hết hạn và truy vấn giao dịch Sandbox chưa nhận callback. Lệnh truy vấn có giới hạn tần suất và idempotency. Repo không tự tạo hoặc thanh toán dịch vụ cron. Giữ tác vụ `expire_bookings` hiện có nếu môi trường đã cấu hình.

## Kiểm tra sau deploy

1. Log build cài thư viện, collectstatic và migration thành công; commit deploy trùng commit vừa push. Kiểm tra `python manage.py check` trong môi trường nếu có Shell.
2. Trang chủ, `/reservations/online/`, `/reservations/online/tra-cuu/` và static tải được, không lỗi manifest/CSRF. Truy cập màn quản lý/bếp bằng tài khoản có quyền.
3. Tạo lịch kiểm thử riêng, chọn giờ đủ xa để giữ chỗ còn ít nhất 5 phút khi yêu cầu ZaloPay. Xác nhận đúng số tiền, nhãn Sandbox, return về hostname Render, callback hoặc Query cập nhật cọc một lần.
4. Đối chiếu món trên hồ sơ và màn món đặt trước. Lịch TABLE hiển thị chờ khách đến; lịch READY có mốc chuẩn bị và nút bếp theo giờ đã chốt. Tra cứu chi tiết cần phiên khách sở hữu liên kết hoặc nhân viên có quyền; mã/SĐT trên thiết bị lạ chỉ hiện trạng thái.
5. Theo dõi log callback, giao dịch pending/review và lỗi server. Chưa kiểm tra trên hosting thì chỉ báo đã push mã nguồn, chưa xác nhận môi trường vận hành đầy đủ.
