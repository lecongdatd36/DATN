# Dự báo số đơn tự cập nhật hằng ngày

Chức năng hiện tại là **demo dữ liệu mô phỏng**, chưa chứng minh chất lượng trên dữ liệu bán hàng thực tế. Không tạo đơn giả trong database. Không thay đổi phân quyền Báo cáo hoặc cách tính doanh thu.

## Luồng cập nhật

Một điểm chạy duy nhất: `scripts/update_forecast_daily.py`, dùng cho cả thủ công và lịch.

1. Lấy ngày hiện tại bằng `Asia/Ho_Chi_Minh`, không phụ thuộc múi giờ máy chạy.
2. Giữ khóa hệ điều hành `artifacts/ai/forecast/update.lock` cho toàn bộ lần cập nhật. Tiến trình thứ hai bỏ qua; khóa tự nhả khi tiến trình kết thúc, kể cả bị dừng. Không xóa file khóa để mở khóa.
3. Với `mo_phong`, bổ sung CSV đến hôm qua bằng seed 42, mốc gốc 30/10/2025 và chuỗi RNG tương thích dữ liệu cũ. Các dòng cũ được giữ nguyên. Không âm thầm vá lỗ hổng ngày hoặc nguồn sai. Với `application_export`, phải cung cấp CSV riêng, không sinh hoặc chuyển sang dữ liệu demo.
4. Tạo thư mục run UUID mới và bản `input.csv` chỉ gồm dữ liệu trước ngày tham chiếu, kết thúc đúng hôm qua, tối thiểu 120 ngày liên tục.
5. Gọi `artifacts/ai/forecast_venv/Scripts/python.exe` huấn luyện Random Forest: đánh giá 4 lượt × 7 ngày trên 28 ngày cuối, mỗi lượt chỉ học dữ liệu trước mốc dự báo; so sánh baseline cùng thứ tuần trước; sau đó học lại toàn bộ dữ liệu. Đặc trưng chỉ dùng quá khứ; dự báo nhiều bước dùng chính dự báo các bước trước để bổ sung lịch sử chưa có thực tế.
6. Kiểm tra nguồn, run ID của metadata/CSV/đánh giá, 7 ngày liên tục bắt đầu đúng ngày tham chiếu, số đơn nguyên không âm, chỉ số hữu hạn, dữ liệu đầu vào và 28 ngày đánh giá. Metadata ràng buộc checksum của input và model. Ghi checksum SHA-256 của toàn bộ artifact vào manifest.
7. Công bố bằng một lần thay thế nguyên tử `current.json` trên cùng filesystem. Web đọc con trỏ đúng một lần rồi đọc CSV/metadata từ thư mục run tương ứng và kiểm tra checksum. Không sao chép từng file sang vị trí dùng chung; không đọc joblib hoặc huấn luyện trong request.

Các thư mục run đã công bố không được sửa hoặc xóa khi web còn dùng. CSV/metadata cũ trong `fixtures/ai/forecast` được giữ để tham khảo, **không còn là đầu vào của Dashboard**.

Nếu chạy lại cùng ngày, nguồn đã có kết quả hợp lệ thì bỏ qua; dùng `--force` để học lại thật và tạo run mới. Nếu chạy qua nửa đêm Việt Nam trước khi công bố, cập nhật thất bại để lần sau chạy lại cho ngày mới. Khi lỗi, con trỏ cũ giữ nguyên, log ghi traceback, web cảnh báo lần cập nhật lỗi và/hoặc kỳ dự báo cũ. Nếu chưa từng có bộ hợp lệ hoặc file đã công bố bị sửa hỏng, web báo chưa có kết quả hợp lệ.

## Chạy thủ công trên Windows

Chạy tại `D:\DOANTOTNGHIEP`:

```powershell
.\.venv\Scripts\python.exe scripts\update_forecast_daily.py --source mo_phong
# Học lại dù đã có kết quả hôm nay:
.\.venv\Scripts\python.exe scripts\update_forecast_daily.py --source mo_phong --force
```

Không cần activate môi trường AI: updater gọi đường dẫn Python AI tuyệt đối. Không cài pandas/sklearn vào `.venv`. Thư viện huấn luyện được mô tả trong `requirements-ai.txt`; không thay đổi bộ thư viện đang có chỉ để chạy lịch. Chương trình huấn luyện riêng `train_order_forecast.py` nhận `--input`, `--output`, `--source`, `--reference-date`, `--run-id`, chỉ ghi kết quả, không công bố; thông thường chỉ gọi updater.

Mở `/bao-cao/` với tài khoản có quyền Báo cáo. Khung AI có kỳ dự báo, ngày dữ liệu học, thời điểm cập nhật thành công, nhãn nguồn và cảnh báo nếu cũ. Từ 00:00 đến lần chạy lúc 07:00, bộ ngày hôm trước được giữ và được đánh dấu cũ; mở Dashboard không kích hoạt huấn luyện.

## Lịch Windows lúc 07:00

```powershell
Get-TimeZone
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\register_forecast_task.ps1
Get-ScheduledTask -TaskName 'QLNH-DailyOrderForecast-mo_phong'
Get-ScheduledTaskInfo -TaskName 'QLNH-DailyOrderForecast-mo_phong'
# Yêu cầu chạy thử tác vụ và sau đó kiểm tra kết quả/log:
Start-ScheduledTask -TaskName 'QLNH-DailyOrderForecast-mo_phong'
Get-ScheduledTaskInfo -TaskName 'QLNH-DailyOrderForecast-mo_phong'
Get-Content .\artifacts\ai\forecast\logs\update.log -Tail 30
```

`Start-ScheduledTask` chỉ yêu cầu chạy, cần chờ kết thúc rồi xem `LastTaskResult` và log. `0` là thành công hoặc đã có kết quả/đang có updater khác; `1` là cập nhật lỗi. Khi chạy bằng tay cần xem `$LASTEXITCODE`.

Script kiểm tra múi giờ trước: Windows `SE Asia Standard Time` = UTC+7, phù hợp Việt Nam. Nếu múi giờ khác UTC+7 hoặc có DST, script dừng và giải thích, không tự sửa giờ/múi giờ hệ thống. Múi giờ Python luôn là `Asia/Ho_Chi_Minh`.

Script dùng một tên tác vụ cố định, cập nhật tác vụ đó khi chạy lại; nếu phát hiện tác vụ cập nhật dự báo khác hoặc tên bị dùng cho hành động khác thì dừng để tránh trùng. Nếu không đọc được Task Scheduler, script dừng trước khi đăng ký. Cần chạy bằng tài khoản Windows có quyền quản lý tác vụ của mình; nếu Windows chặn, mở PowerShell có quyền phù hợp bằng chính tài khoản sở hữu dự án.

Lịch gồm 07:00 mỗi ngày và lúc tài khoản đăng nhập, có `StartWhenAvailable` để chạy bù, `IgnoreNew` để không mở thêm instance, retry 3 lần cách 15 phút khi lỗi. Khóa trong Python vẫn bảo vệ cả lần chạy thủ công. Thiết lập dựa trên [Microsoft: ScheduledTaskSettings](https://learn.microsoft.com/en-us/powershell/module/scheduledtasks/new-scheduledtasksettingsset) và [ScheduledTaskTrigger](https://learn.microsoft.com/en-us/powershell/module/scheduledtasks/new-scheduledtasktrigger).

**Máy phải bật và tài khoản đăng ký phải đang đăng nhập.** Máy ngủ/tắt không bảo đảm chạy đúng 07:00; chạy bù khi máy khả dụng và khi đăng nhập. Không lưu mật khẩu. Muốn chạy khi đã đăng xuất cần cấu hình tài khoản dịch vụ/quyền riêng trong Task Scheduler; script này dùng `Interactive`, không hứa chạy khi đăng xuất. Không cần Django runserver hoặc VS Code đang mở. Runner PowerShell chạy ẩn và trả nguyên exit code của updater.

## Vị trí dữ liệu và log

```text
artifacts/ai/forecast/
  daily_orders_demo_v1.csv             # CSV demo, chỉ bổ sung
  update.lock                         # khóa chung, không xóa
  logs/update.log                     # log điều phối, xoay 5MB × 5 bản
  logs/<run_id>.log                    # stdout/stderr huấn luyện của từng run
  mo_phong/current.json                # con trỏ demo + checksum
  mo_phong/last_failure.json           # lần thất bại gần nhất (nếu có)
  mo_phong/runs/<run_id>/
    input.csv
    forecast_demo.joblib
    du_bao_7_ngay.csv
    evaluation.json
    kiem_tra_du_bao.csv
  application_export/                 # con trỏ/lịch sử nguồn ứng dụng riêng
```

Tên `forecast_demo.joblib` được giữ tương thích output cũ; phải dựa vào `data_source`/run ID trong metadata, không suy luận nguồn từ tên file. `last_failure.json` có thể được giữ sau khi cập nhật lại thành công, nhưng web chỉ cảnh báo nếu thời điểm lỗi mới hơn thời điểm công bố thành công. Log điều phối dùng giờ máy, còn ngày kỳ dự báo và timestamp trong metadata/manifest dùng giờ Việt Nam.

`ORDER_FORECAST_ROOT` trong `.env` cho phép web đọc thư mục khác, `ORDER_FORECAST_SOURCE=mo_phong` là mặc định. Updater không tự đọc `.env`: nếu đổi root, phải truyền cùng đường dẫn bằng `--root`; nếu đổi nguồn web, phải chỉ định `--source` tương ứng. Restart Django khi thay cấu hình; công bố run mới không cần restart. Không tự trộn hoặc fallback giữa các nguồn.

## Nguồn ứng dụng để phát triển tiếp

Exporter chỉ truy vấn: đếm đơn gốc hoàn tất, theo ngày mở đơn trong giờ Việt Nam, đã đóng trước mốc ngày tham chiếu; không chèn/sửa nghiệp vụ. Phải tự xác nhận ngày bắt đầu quan sát của ứng dụng. Trong khoảng đã xác nhận, ngày truy vấn không có đơn được xuất số 0; đây là số đếm database, không phải số demo. Không đặt mốc sớm giả tạo để vượt yêu cầu 120 ngày. CSV đầu vào thiếu ngày hoặc thiếu hôm qua bị từ chối.

```powershell
$observedFrom = Read-Host 'Ngay bat dau quan sat du lieu ung dung (yyyy-MM-dd)'
$exportStamp = Get-Date -Format 'yyyyMMdd_HHmmss_fff'
$applicationCsv = "artifacts/ai/forecast/application_input/orders_$exportStamp.csv"
.\.venv\Scripts\python.exe scripts\export_daily_orders.py --start-date $observedFrom --output $applicationCsv
if ($LASTEXITCODE -eq 0) {
    .\.venv\Scripts\python.exe scripts\update_forecast_daily.py --source application_export --input $applicationCsv
}
```

Chỉ đổi web sang `ORDER_FORECAST_SOURCE=application_export` khi chủ động muốn dùng nguồn đó. Tác vụ Windows cung cấp hiện chạy demo; không tự đổi lịch hoặc dữ liệu sang ứng dụng. Nguồn ứng dụng cần exporter chạy trước updater mỗi ngày trên đúng database và cần đánh giá định nghĩa số đơn/chất lượng riêng.

## Kiểm thử

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test apps.reports.tests ai_tools.tests.test_forecast_update --settings=QLNH.test_settings
.\artifacts\ai\forecast_venv\Scripts\python.exe -m unittest scripts.test_order_forecast_training -v
# Thử ngày khác ở root RIÊNG, không sửa thời gian hệ thống hoặc kỳ thật:
.\.venv\Scripts\python.exe scripts\update_forecast_daily.py --root artifacts/ai/forecast_test --reference-date 2026-12-12
.\.venv\Scripts\python.exe scripts\update_forecast_daily.py --root artifacts/ai/forecast_test --reference-date 2026-12-13
```

Các test bao gồm chuyển tháng/năm/năm nhuận; giữ seed và ngày cũ; loại dữ liệu tương lai khỏi snapshot; thiếu/trùng ngày, âm/sai nguồn; nguồn ứng dụng không fallback; CSV/metadata/run sai; lỗi trainer/công bố giữ bộ cũ; khóa hai tiến trình và nhả khóa khi chết; lặp cùng ngày; đọc liên tục trong khi công bố nhiều lần; stale/failure trên template; context Dashboard đọc run mới; phân quyền và bộ lọc doanh thu; đặc trưng trễ và đánh giá cuốn chiếu không thấy tương lai. Windows có retry ngắn, giới hạn khi đọc/thay con trỏ gặp lỗi chia sẻ file thoáng qua. Đây là kiểm thử logic và HTML server, không thay thế kiểm tra bố cục bằng trình duyệt.

### Kết quả thực hiện ngày 30/10/2026

- `manage.py check`: không có lỗi.
- 21 test cập nhật/đọc kết quả/Dashboard: qua, không cần tạo hoặc ghi database kiểm thử.
- 3 test đặc trưng trễ, đệ quy và đánh giá trong môi trường AI: qua.
- Huấn luyện thật nhiều lần cho ngày hiện tại; mỗi lần force tạo run mới và giữ nguyên run trước. Dashboard với tài khoản có quyền trả HTTP 200, context và HTML đọc run mới, kỳ 30/10–05/11/2026; báo cáo doanh thu vẫn trả context hợp lệ. Bộ artifact cuối cùng được kiểm tra cả checksum input/model và manifest. Không đăng nhập bằng cách ghi session mới.
- Huấn luyện thật riêng cho 12/12, 13/12, 31/12/2026 và 01/01/2027: đầu vào kết thúc đúng hôm trước, mỗi lần tạo đúng 7 ngày và artifact mới. Tổng hợp cục bộ: `artifacts/ai/forecast_validation_20261030_182531/validation_summary.json`. Dữ liệu/ngày kiểm thử không công bố vào root thật.
- Xác nhận `.venv` không có pandas/sklearn; không cài thêm thư viện web.
- Runner PowerShell chạy thật: qua và nhận biết kết quả hôm nay đã có. Script đăng ký lịch được kiểm tra cú pháp; chạy `-WhatIf` dừng tại `Get-ScheduledTask` với `Access denied` (`0x80041003`). **Chưa đăng ký tác vụ, chưa kiểm chứng lịch chạy thực tế.** Script hoàn chỉnh ở `scripts/register_forecast_task.ps1` để chạy ngoài phiên công cụ này.
- Múi giờ Windows thực tế: `SE Asia Standard Time`, UTC+7. Không sửa thời gian hệ thống; không triển khai hosting; chưa kiểm tra trực quan bằng trình duyệt.

## Hosting: chỉ hướng dẫn, chưa triển khai

Worker lịch và web phải dùng chung **thư mục lưu trữ bền vững**, cùng root và nguồn. Worker có môi trường AI riêng; web chỉ cần thư viện chuẩn để đọc JSON/CSV. Không đưa scheduler vào mỗi web worker, không huấn luyện khi xử lý HTTP. Trên filesystem tạm/không dùng chung, cập nhật từ cron sẽ không tự xuất hiện trên web.

Ví dụ scheduler dùng UTC: chạy `0 0 * * *` tương ứng 07:00 Việt Nam; hoặc dùng cron hỗ trợ timezone với `CRON_TZ=Asia/Ho_Chi_Minh` và `0 7 * * *`. Lệnh là `<python-dieu-phoi> /duong-dan/scripts/update_forecast_daily.py --source mo_phong --root <thu-muc-dung-chung> --ai-python <python-AI>`. Thiết lập cơ chế chạy bù/retry của hosting vì cron thường không tự chạy bù. Với nhiều máy/host không dùng chung khóa filesystem tin cậy, phải thêm khóa phân tán và cơ chế công bố trên storage phù hợp trước khi mở rộng. Chưa thay đổi hoặc triển khai hosting.
