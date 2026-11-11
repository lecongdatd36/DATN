# Giao diện trang khách Cơm Quê

Nhánh: `feature/com-que-homepage-refresh`.

## Banner, giỏ món và combo

Banner hiện phủ ngang màn hình và cao theo viewport ở desktop; mobile giữ phần ảnh/chữ trọn màn hình rồi tới form đặt bàn. Chữ dùng Dancing Script có bộ ký tự tiếng Việt, tải từ kho Google Fonts và phục vụ tại `static/customer/fonts/`; giữ giấy phép OFL đi kèm. Nguồn: https://github.com/google/fonts/tree/main/ofl/dancingscript.

Nút `+` trên món lẻ và combo cập nhật giỏ qua API `/reservations/online/gio-mon/`, có CSRF, kiểm tra số lượng, trạng thái món/thành phần và tính giá từ máy chủ. Giỏ lưu trong phiên Django, dùng chung giữa trang chủ và `/menu/`, không giữ bàn hoặc trừ kho. Khách có giỏ từ trang khách đi vào form thông tin đặt bàn, rồi tới kiểm tra giỏ/cọc; khách chưa chọn món vẫn có luồng chỉ đặt bàn như trước. Giỏ chỉ được xóa khỏi bản nháp sau khi tạo lịch thành công. Trên các bước đặt bàn, dùng giỏ riêng của luồng này để tránh hai bộ điều khiển cùng sửa một bản nháp.

### Quản lý combo

- Trang quản lý: `/thuc-don/combo/`, quyền `menu.manage_menu`; có thêm, sửa, bật/tắt, kiểm tra phiên bản và nhật ký.
- `menu.Combo` lưu mã, tên, giới thiệu, số người, giá bán và trạng thái. `ComboItem` chứa 2–12 món, số phần mỗi món 1–10. Giá combo không vượt tổng giá lẻ tại lúc mở bán; combo có thành phần hết/ngừng bán sẽ không đặt được.
- Combo được tách thành món thành phần khi tạo `PreorderItem`, để bếp, kho và chi phí dùng các quy trình hiện có. Giá combo được phân bổ thành số đồng nguyên theo tỷ trọng, bảo đảm tổng tiền đúng tuyệt đối và từng phần có giá dương. Có thể tách hai dòng cùng món chênh 1đ khi cần làm tròn. Hóa đơn không cộng giá combo lần thứ hai.
- `Reservation.combo_snapshot` và thông tin combo trên `PreorderItem` giữ tên, số combo, thành phần và giá của lịch đặt. Chỉnh combo trên catalog không sửa lịch/đơn đã có. Nhận khách giữ giá đã phân bổ của combo, kể cả khi chọn xác nhận lại giá món lẻ.
- Combo READY chỉ được chốt khi tất cả món thành phần được cho phép chuẩn bị trước; giữ/xuất nguyên liệu theo các phần món. Nhận khách không xuất kho lần hai.
- Không xóa combo qua UI; ngừng bán để giữ đối chiếu với lịch cũ.

### Combo khởi tạo trên local

Đã tạo từ thực đơn đang có: **Hẹn hò vị nhà** (2 người, 196.000đ), **Sum vầy bốn người** (4 người, 455.000đ), **Bạn bè quây quần** (6 người, 695.000đ). Giá khởi tạo khoảng 90% tổng giá lẻ, làm tròn tới 1.000đ. Quản lý có thể đổi tên, món và giá trong màn combo.

```sh
python manage.py migrate
python manage.py seed_combos --actor <username-quan-ly>
```

Lệnh chỉ tạo mã combo chưa tồn tại, không ghi đè combo hoặc đơn cũ; thiếu món thành phần thì bỏ qua. Dữ liệu combo local không tự lên hosting theo Git: tạo qua UI quản lý hoặc chạy lệnh trên đúng môi trường khi đã kiểm tra thực đơn.

### Kiểm thử bổ sung

`apps/menu/tests/test_combos.py` kiểm tra quyền, phiên bản, rollback, số lượng tổng, giá giả từ client, làm tròn giá, cô lập giỏ theo phiên, CSRF, giá lịch cũ sau sửa catalog và kho khi chuẩn bị/nhận khách. `scripts/verify_storefront_combos.py` chạy Chrome qua giỏ → đặt bàn → đồng ý → thông báo cọc có chữ ký từ cổng mô phỏng local → sửa giá combo trong quản lý → nhận khách/POS. Mọi lịch, đơn và tiền thử của script nằm trong PostgreSQL UUID riêng rồi được dọn; không gọi cổng ngân hàng bên ngoài. Ảnh kiểm tra lưu ở `artifacts/homepage-preview/combos/`.

Kết quả cuối: **590 test Django qua**, Chrome qua ở desktop/mobile/tablet, `manage.py check` không lỗi, migration khớp models. Đã so khớp dấu vân tay các bảng lịch đặt/đơn/món/hóa đơn/thanh toán local với trước khi migrate: dữ liệu cũ không thay đổi. Chỉ thêm schema combo và ba bản ghi combo mới kèm nhật ký catalog. Collectstatic ở `DEBUG=False` kiểm tra được manifest cho CSS, giỏ, font và banner.

Giữ màu đỏ thương hiệu `#b71932`, kem ấm và điểm vàng nhạt. Tham khảo bố cục người dùng cung cấp, thay phần ưu đãi/đánh giá mẫu bằng nội dung có sẵn của nhà hàng. Header dùng chung có tìm món thực tế; trang chủ có form ngày/giờ/số người chuyển sang form đặt bàn hiện có, không tạo lịch hoặc giữ bàn bằng GET. Thẻ món dùng ảnh, giá và trạng thái từ database. Bộ lọc danh mục và xem thêm hoạt động bằng JavaScript; tắt JS vẫn xem được toàn bộ món.

## Banner thực đơn và tiếng Anh

Trang `/menu/` dùng chung component `templates/customer/includes/welcome_banner.html` với trang chủ: ảnh tràn chiều ngang, chiều cao theo màn hình, chữ Dancing Script có dấu và form đặt bàn nhanh. Nội dung riêng cho thực đơn vẫn giữ màu đỏ Cơm Quê và nền kem.

Nút **VI / EN** trên header dùng Django i18n và cookie ngôn ngữ. Đổi ngôn ngữ giữ đường dẫn, bộ lọc, giỏ món và bản nháp đặt bàn. Không thêm tiền tố URL để tránh đổi các địa chỉ callback thanh toán và liên kết đặt bàn đã phát hành. Phần khách hàng, giỏ JavaScript, đặt bàn, thông báo xác thực và kết quả thanh toán có bản tiếng Anh; màn quản trị nội bộ vẫn dùng tiếng Việt. Nội dung người dùng nhập và ghi chú lịch sử giữ nguyên.

Tên/giới thiệu tiếng Anh có ô riêng trong quản lý món, danh mục, đơn vị và combo. Nếu ô tiếng Anh trống thì dùng tên gốc; giá và số lượng không thay đổi theo ngôn ngữ. Lệnh khởi tạo chỉ điền ô đang trống cho những món/combo đã biết, không ghi đè bản dịch tùy chỉnh hay sửa đơn, cọc và hóa đơn cũ:

```sh
python manage.py migrate
python manage.py seed_menu_english
python scripts/compile_translations.py
python manage.py collectstatic --no-input
```

Migration bổ sung `menu/0007`. Catalog UI nằm trong `locale/en/LC_MESSAGES/django.po`, JavaScript trong `djangojs.po`; chỉnh bản dịch rồi chạy compiler để cập nhật `.mo`. `build.sh` tự biên dịch trước collectstatic, không cần cài GNU gettext trên Windows/Render. Dữ liệu bản dịch tên món lưu trong database từng môi trường; Git chỉ mang schema, catalog UI và lệnh khởi tạo.

Kiểm tra bổ sung: **597 test Django qua**, `scripts/verify_storefront_combos.py --language` qua với Chrome ở desktop/mobile/tablet, chuyển VI → EN → VI → EN khi giỏ có món, tìm tên tiếng Anh, xác thực form và giỏ/combo đến nhận khách. Script dùng PostgreSQL tạm riêng, cọc có chữ ký từ fixture local, không gọi ngân hàng bên ngoài. Ảnh nằm trong `artifacts/homepage-preview/language/`.

## Nguồn ảnh banner

- Công cụ: built-in image_gen qua skill imagegen, chế độ generate.
- Tệp dùng trong website: `static/customer/images/com-que-table-hero-v1.webp`.
- Bản PNG nguồn lưu local trong `artifacts/homepage-preview/com-que-table-hero-v1.png` (Git bỏ qua).
- Ảnh minh họa bàn ăn Việt, không phải ảnh không gian thật của nhà hàng hay ảnh chính xác của một món đang bán. Không thay ảnh món trong database.
- PNG được chuyển định dạng WebP để giảm dung lượng, không chỉnh nội dung.

Prompt cuối:

> Use case: photorealistic-natural. Asset type: wide website hero background for a warm Vietnamese family restaurant, Cơm Quê. Create a refined editorial food photograph, panoramic 2560 x 960 composition. A welcoming rustic dark walnut dining table with a beautiful ivory ceramic plate of Vietnamese grilled pork with rice and fresh cucumber, a small plate of spring rolls and fresh herbs, subtle little dipping sauce bowl, understated ivory linen and a folded burgundy cloth napkin. Natural appetizing food, honest home cooking presented with care, tactile ceramic and wood, warm late afternoon side light, soft shadows, subtle filmic depth, tasteful restrained food magazine photography. Composition is crucial: the left 36 percent is dark quiet walnut table and atmospheric negative space for white headline overlay; the main hero plate occupies the center at approximately 58 percent across, clearly visible in the middle band of the panorama; the far right is softly blurred unobtrusive table because a booking UI will overlay it. Camera at a low three-quarter overhead angle. Warm brown, toasted gold, ivory, deep burgundy palette, no bright green dominant backdrop. No people, no restaurant interior claims, no words, no logos, no watermark, no text or graphic elements, no ornate luxury props, no collage. High-resolution sharp food texture suitable for a large web banner.

## Kiểm tra

- Django check; test trang chủ và luồng đặt bàn, gồm GET gợi ý hợp lệ/không hợp lệ, giữ nguyên nháp và không tạo lịch khi chỉ mở form.
- Chrome headless trên localhost: desktop 1440, tablet 768, mobile 390; ảnh thực đơn tải được, bộ lọc, xem thêm, menu mobile, form đặt nhanh chuyển đúng thông tin và header trang thực đơn.
- Screenshot trong `artifacts/homepage-preview/`; trình preview chặn POST, không tạo đơn/thu tiền thử trong database nhà hàng.
