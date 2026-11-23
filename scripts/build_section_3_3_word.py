"""Author section 3.3 using the retained section 3.2 Word format."""
import ast
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile
from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs'/'section-3-3'
SHOTS=OUT/'screenshots'
QA=ROOT/'artifacts'/'section-3-3-word-qa'
QA.mkdir(parents=True,exist_ok=True)
REFERENCE=ROOT/'docs'/'section-3-2'/'Muc_3_2_Xay_dung_co_so_du_lieu.docx'
reference_sha=hashlib.sha256(REFERENCE.read_bytes()).hexdigest()
doc=Document(REFERENCE)
sec=doc.sections[0]
with ZipFile(REFERENCE) as archive:
    preserved={name:hashlib.sha256(archive.read(name)).hexdigest() for name in archive.namelist() if name.startswith(('word/styles','word/numbering','word/theme','word/footer','word/header'))}
contract=f'''# Section 3.3 artifact contract

Reference: {REFERENCE}
SHA-256: {reference_sha}
Reference: 11 pages, one section. All reference pages were rendered in the previous task and inspected; retained PNGs: artifacts/section-3-2-word-qa/page-1.png through page-11.png.
Page: portrait Letter 8.5 x 11 inches, margins left {sec.left_margin/914400:.4f}, right {sec.right_margin/914400:.4f}, top/bottom {sec.top_margin/914400:.4f} inches. Preserve section properties and footer PAGE field.
Typography: Times New Roman; Normal 13 pt, justified, first-line 0.3 inches, 1.3 line spacing, 6 pt after. Heading 1 15 pt, Heading 2 14 pt, black and bold. Captions 12 pt, centered. Tables 11.5 pt with pale-gray headers, D9D9D9 borders, automatic row height, repeated header, no split rows.
Editable slot: replace the entire main document body with section 3.3 and its supplied subject areas. Keep styles, theme, numbering, footer, section geometry unchanged. Remove old body image relationships; insert new screenshot relationships.
Figures: real application UI, synthetic fixtures only, two mobile screenshots per plate, proportional size, original pixels. Figures in this section run from 3.3 to 3.7; the employee update evidence is shown as subfigures 3.3a and 3.3b. Tables start at 3.6.
Content: ten subsections corresponding to the user's ten functional areas. No placeholders, invented features, source-code paths in the report, production personal data, or passwords. Source evidence: docs/section-3-3/ui-evidence.json.
QA: render with the packaged renderer first. The installed managed Windows runtime has libreOfficeVersion null; if the same missing-soffice error recurs, use a separate hidden Word instance to export read-only, then the managed Poppler to render PNGs. Inspect all final pages. Compare preserve-only package hashes and reference SHA-256.
'''
(QA/'artifact.md').write_text(contract,encoding='utf-8')
(QA/'preserve-parts.json').write_text(json.dumps(preserved,indent=2),encoding='utf-8')
for child in list(doc._element.body):
    if child.tag!=qn('w:sectPr'):doc._element.body.remove(child)
for key,rel in list(doc.part.rels.items()):
    if rel.reltype.endswith('/image'):doc.part.drop_rel(key)

# Reuse the existing, visually verified paragraph and table builders verbatim.
tree=ast.parse((ROOT/'scripts'/'build_section_3_2_word.py').read_text(encoding='utf-8'))
helpers=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in {'p','heading','lead','table'}]
exec(compile(ast.Module(body=helpers,type_ignores=[]),'retained-format-helpers','exec'),globals())


def plate(left,right,caption):
    para=doc.add_paragraph()
    para.paragraph_format.first_line_indent=Inches(0)
    para.paragraph_format.space_before=Pt(7)
    para.paragraph_format.space_after=Pt(4)
    para.paragraph_format.line_spacing=1
    para.paragraph_format.keep_with_next=True
    para.alignment=WD_ALIGN_PARAGRAPH.CENTER
    for index,name in enumerate((left,right)):
        if index:para.add_run('   ')
        shape=para.add_run().add_picture(str(SHOTS/(name+'.png')),width=Inches(2.80))
        shape._inline.docPr.set('descr',caption+(' — ảnh bên trái' if index==0 else ' — ảnh bên phải'))
    cap=doc.add_paragraph(caption,'Caption')
    cap.alignment=WD_ALIGN_PARAGRAPH.CENTER
    cap.paragraph_format.keep_with_next=True
    source=doc.add_paragraph('Nguồn: giao diện ứng dụng với dữ liệu kiểm thử riêng, ngày 20/11/2026.')
    source.paragraph_format.first_line_indent=Inches(0)
    source.paragraph_format.space_after=Pt(7)
    source.paragraph_format.line_spacing=1
    source.alignment=WD_ALIGN_PARAGRAPH.CENTER
    for run in source.runs:run.font.size=Pt(10);run.italic=True


heading('3.3. Xây dựng hệ thống quản lý',1)
p('Trên cơ sở các mô hình dữ liệu đã cài đặt, hệ thống quản lý nhà hàng Cơm Quê được xây dựng thành các phân hệ phục vụ quản lý, nhân viên phục vụ, bếp, thu ngân và thủ kho. Mỗi chức năng bao gồm giao diện nhập hoặc tra cứu, xử lý nghiệp vụ tại máy chủ và cập nhật dữ liệu theo quyền của người sử dụng. Giao diện được bố trí phù hợp với máy tính và thiết bị di động để hỗ trợ thao tác trong quá trình phục vụ tại nhà hàng.')
p('Các chức năng dùng chung dữ liệu về bàn, lịch phục vụ, món, đơn hàng và chứng từ. Việc thay đổi trạng thái được kiểm tra tại máy chủ, có phản hồi rõ ràng khi thành công hoặc không thỏa điều kiện. Các hình minh họa trong mục này được chụp trực tiếp từ ứng dụng với dữ liệu kiểm thử tách riêng, nhằm thể hiện kết quả xử lý mà không sử dụng thông tin cá nhân hoặc giao dịch vận hành thực tế.')

heading('3.3.1. Xây dựng chức năng đăng nhập và phân quyền')
p('Màn hình đăng nhập tiếp nhận tên đăng nhập và mật khẩu, thực hiện xác thực bằng cơ chế của Django. Khi thông tin không hợp lệ hoặc tài khoản bị khóa, hệ thống trả thông báo chung và giữ người dùng tại biểu mẫu đăng nhập. Sau khi xác thực thành công, phiên đăng nhập được thiết lập để nhận diện người sử dụng trong các yêu cầu tiếp theo. Đăng xuất được thực hiện bằng yêu cầu POST có kiểm tra CSRF, kết thúc phiên hiện tại và thông báo kết quả cho người dùng (Django Software Foundation, tài liệu Using the Django authentication system).')
p('Quyền sử dụng được tổ chức thông qua nhóm quyền và các quyền nghiệp vụ. Người quản lý được chuyển tới không gian quản lý; nhân viên bếp tới màn hình bếp; thủ kho tới không gian kho; phục vụ và thu ngân được điều hướng tới giao diện bán hàng phù hợp với thiết bị. Việc ẩn hoặc hiện nút chỉ hỗ trợ cách trình bày. Mỗi yêu cầu truy cập hoặc thay đổi dữ liệu vẫn được kiểm tra quyền tại máy chủ; người đã đăng nhập nhưng không có quyền bị từ chối khi truy cập trực tiếp địa chỉ chức năng.')
table('Bảng 3.6. Quyền xem một số màn hình theo nhóm mặc định',['Nhóm quyền','Nhân sự','Báo cáo','Kho','Thực đơn'],[
    ('Quản lý','Có','Có','Có','Có'),('Phục vụ','Không','Không','Không','Có'),('Bếp','Không','Không','Không','Có'),('Thu ngân','Không','Không','Không','Có'),('Thủ kho','Không','Không','Có','Không'),
],[1.45,1.20,1.20,1.20,1.48])
for row in doc.tables[-1].rows:
    for cell in row.cells[1:]:
        for para in cell.paragraphs:para.alignment=WD_ALIGN_PARAGRAPH.CENTER
p('Bảng 3.6 phản ánh quyền xem màn hình, không đồng nhất quyền xem với quyền thêm, sửa, xác nhận hoặc thu tiền. Chẳng hạn, phục vụ có thể xem danh mục món phục vụ gọi món nhưng không vì vậy được phép thay đổi giá. Các chức năng quản lý tài khoản còn kiểm tra đối tượng bị tác động; quyền quản lý thông thường không mặc nhiên cho phép sửa tài khoản quản trị cấp cao hoặc nâng quyền cho chính mình.')
plate('login','manager','Hình 3.3a. Màn hình đăng nhập và không gian của người quản lý')

heading('3.3.2. Xây dựng chức năng quản lý nhân viên')
p('Phân hệ nhân viên hiển thị mã, họ tên, vị trí công việc, trạng thái làm việc và trạng thái tài khoản. Danh sách hỗ trợ tìm kiếm, lọc theo vị trí, trạng thái và phân trang 20 bản ghi. Chức năng thêm nhân viên được liên kết với quy trình tạo tài khoản, qua đó tạo hồ sơ và tài khoản tương ứng trong cùng một nghiệp vụ, hạn chế sai lệch liên kết giữa hai đối tượng.')
p('Biểu mẫu kiểm tra tên đăng nhập, điện thoại, vị trí công việc và các mốc ngày. Điện thoại của hồ sơ được kiểm tra định dạng và tính duy nhất; ngày vào làm không được nằm trong tương lai. Khi chuyển sang trạng thái đã nghỉ việc, ngày nghỉ phải hợp lệ so với ngày vào làm và thời điểm hiện tại. Các trường được phép cập nhật được xác định rõ trong biểu mẫu và hàm xử lý, nên việc gửi thêm trường ngoài giao diện không tự mở rộng quyền cập nhật (Django Software Foundation, tài liệu Creating forms from models).')
p('Khi khóa tài khoản hoặc ghi nhận nghỉ việc, hệ thống không xóa các giao dịch trước đó. Phiên bản phiên đăng nhập được sử dụng để làm mất hiệu lực phiên cũ khi có thay đổi cần thiết. Các thao tác tạo, sửa, đổi vị trí và thay đổi trạng thái được ghi nhật ký. Hình 3.3b minh họa sự khác biệt của không gian bếp và thông báo thành công sau một yêu cầu cập nhật nhân viên đã được lưu thực tế.')
plate('kitchen','employee-updated','Hình 3.3b. Không gian bếp và kết quả cập nhật nhân viên')

heading('3.3.3. Xây dựng chức năng quản lý khách hàng')
p('Phân hệ khách hàng quản lý hồ sơ liên hệ, hạng thành viên và thông tin chi tiêu phục vụ chăm sóc khách hàng. Nhân viên có quyền có thể tìm kiếm, xem chi tiết và cập nhật hồ sơ theo phạm vi được cấp. Số điện thoại được chuẩn hóa trước khi đối chiếu để hạn chế việc một thông tin liên hệ bị ghi thành nhiều dạng khác nhau. Lịch đặt và đơn hàng liên quan được sử dụng để truy vết quá trình phục vụ.')
p('Khách truy cập kênh đặt chỗ trực tuyến không bắt buộc có tài khoản nhân viên. Quyền xem chi tiết yêu cầu đặt chỗ được kiểm tra bằng phiên tạo yêu cầu hoặc mã truy cập riêng. Mã đặt chỗ dễ đọc và số điện thoại không được xem là căn cứ duy nhất để cấp quyền xem thông tin chi tiết. Cơ chế này phù hợp với phiên truy cập ẩn danh của Django và tránh đồng nhất tài khoản nội bộ với người đặt bàn (Django Software Foundation, tài liệu How to use sessions).')
p('Khi hồ sơ khách hàng đã liên quan tới giao dịch, việc xử lý thay đổi phải giữ khả năng đối chiếu lịch sử. Hạng thành viên và mức giảm được xác định theo chính sách tại thời điểm tính tiền; các giá trị áp dụng cho hóa đơn được lưu lại để việc cập nhật hồ sơ hoặc chính sách sau này không làm thay đổi giao dịch đã chốt.')

heading('3.3.4. Xây dựng chức năng quản lý bàn và lịch đặt')
p('Màn hình bàn thể hiện mã bàn, khu vực, số chỗ và trạng thái vận hành. Các bộ lọc theo khu vực hoặc trạng thái hỗ trợ nhân viên quan sát tình hình phục vụ. Trạng thái hiện tại của bàn được phân biệt với khả năng nhận lịch ở một khoảng thời gian tương lai: bàn đang trống không có nghĩa còn trống ở mọi khung giờ, còn bàn có lịch ngày hôm sau vẫn có thể phục vụ khách ở thời điểm hiện tại.')
p('Chức năng tìm bàn tiếp nhận giờ đến, số khách và điều kiện khu vực. Máy chủ loại các bàn hoặc khu vực ngừng sử dụng, bàn không đủ sức chứa và những bàn có lịch chặn trong khoảng yêu cầu, sau đó trả danh sách được xếp hạng. Kết quả tìm kiếm là thông tin tại thời điểm tra cứu. Khi xác nhận, ứng dụng kiểm tra lại dữ liệu trong cơ chế giao dịch và khóa đã trình bày ở mục 3.2 để xử lý trường hợp bàn vừa được người khác đặt.')
p('Lịch đặt lưu các trạng thái chờ xác nhận, đã xác nhận, đang phục vụ, hoàn tất, đã hủy và không đến. Nhận khách chỉ được thực hiện khi khách thực sự đến; hoàn tất lượt phục vụ phải đáp ứng điều kiện liên quan đến đơn và bàn. Việc sửa hoặc chuyển bàn kiểm tra phiên bản dữ liệu, trạng thái lịch, sức chứa và lịch của bàn đích. Nhật ký cho phép tra cứu các thay đổi đã thực hiện. Hình 3.4 minh họa bàn ở các trạng thái và một lịch bốn khách đã xác nhận tại bàn B02.')
plate('tables','booking-confirmed','Hình 3.4. Giao diện quản lý bàn và lịch đặt')

heading('3.3.5. Xây dựng chức năng quản lý món ăn')
p('Phân hệ thực đơn cho phép quản lý mã món, tên, nhóm món, đơn vị bán, đơn giá, mô tả, hình ảnh và trạng thái. Danh sách hỗ trợ tìm theo mã hoặc tên, lọc nhóm, đơn vị và tình trạng phục vụ. Chức năng quản lý danh mục được tách với thao tác báo còn hoặc hết món để nhân viên chỉ thực hiện công việc phù hợp với quyền được cấp.')
p('Ảnh tải lên được kiểm tra ở máy chủ thay vì chỉ dựa vào phần mở rộng tên tệp. Chương trình chấp nhận ảnh tĩnh JPEG, PNG hoặc WebP, giới hạn dung lượng 5 MB và không vượt 20 triệu điểm ảnh. Ảnh được giải mã, kiểm tra và tạo lại dưới dạng WebP với kích thước giới hạn; bản chính tối đa 1.200 điểm ảnh mỗi chiều và ảnh thu nhỏ tối đa 320 điểm ảnh. Quy trình tạo lại loại bỏ các dữ liệu mô tả ảnh không cần thiết trước khi lưu.')
p('Khi gọi món, điều kiện phục vụ được kiểm tra lại từ dữ liệu phía máy chủ, bao gồm trạng thái món và các danh mục liên quan. Đối với món bật theo dõi kho, định mức và lượng nguyên liệu khả dụng còn được kiểm tra khi gửi bếp. Thay đổi giá hoặc tên danh mục không cập nhật ngược dòng món đã ghi nhận. Món không tiếp tục kinh doanh được chuyển sang trạng thái phù hợp để vẫn giữ liên kết với giao dịch cũ.')

heading('3.3.6. Xây dựng chức năng quản lý đơn hàng')
p('Đơn hàng tập hợp bàn phục vụ, khách hàng khi có liên kết, thời điểm mở, người thực hiện và các dòng món. Khi thêm món, ứng dụng lấy đơn giá hợp lệ từ cơ sở dữ liệu, lưu mã, tên, đơn vị và giá tại thời điểm ghi nhận. Số tiền gửi từ trình duyệt không được sử dụng như nguồn giá có thẩm quyền. Các thao tác sửa số lượng, ghi chú, hủy món hoặc gửi bếp đều kiểm tra trạng thái và phiên bản đơn hiện tại.')
table('Bảng 3.7. Trạng thái đơn hàng và ý nghĩa xử lý',['Trạng thái','Nhãn hiển thị','Ý nghĩa'],[
    ('OPEN','Đang mở','Đơn đã được mở, có thể tiếp nhận món theo điều kiện hiện tại.'),
    ('IN_PROGRESS','Đang phục vụ','Đơn đang trong quá trình chế biến hoặc phục vụ.'),
    ('PAYMENT_REQUESTED','Yêu cầu thanh toán','Đơn chuyển sang giai đoạn xử lý thanh toán.'),
    ('COMPLETED','Hoàn tất','Nghiệp vụ thanh toán đơn đã được hoàn tất.'),
    ('CANCELLED','Đã hủy','Đơn được hủy theo điều kiện nghiệp vụ và lưu lý do.'),
],[2.00,1.50,3.03])
p('Trạng thái dòng món được quản lý riêng với trạng thái đơn, gồm nháp, chờ chế biến, đang chế biến, đã sẵn sàng, đã phục vụ và đã hủy. Nhờ đó, một đơn có thể chứa các dòng món ở những bước khác nhau. Màn hình bếp tập trung vào món, số lượng, bàn và ghi chú chế biến; các bước chuyển trạng thái được ghi nhận bằng thao tác xác định và thời điểm tương ứng.')
p('Trường revision hỗ trợ phát hiện biểu mẫu đã cũ khi nhiều nhân viên cùng mở một đơn. Khi điều kiện không còn phù hợp, máy chủ trả thông báo để người dùng tải lại trạng thái. Hình 3.5 thể hiện danh mục món và đơn tại bàn B03, trong đó hai phần cơm gà có đơn giá 65.000 đồng, thành tiền 130.000 đồng và đang chờ chế biến.')
plate('menu','order','Hình 3.5. Giao diện quản lý món ăn và đơn hàng')

heading('3.3.7. Xây dựng chức năng quản lý nguyên liệu và kho')
p('Màn hình kho hiển thị mã, tên, đơn vị cơ sở, số lượng tồn, ngưỡng cảnh báo và giá vốn bình quân của nguyên liệu. Chức năng tìm kiếm và lọc nguyên liệu sắp hết hỗ trợ theo dõi nhu cầu bổ sung. Dữ liệu định mức liên kết món với nguyên liệu để tính lượng tiêu hao khi chế biến; định mức và tồn phải sử dụng cùng đơn vị của từng nguyên liệu, vì hệ thống chưa có mô hình quy đổi đơn vị tự động.')
p('Phiếu nhập gồm nhà cung cấp, thông tin chứng từ, ghi chú và các dòng nguyên liệu. Người có quyền bổ sung hoặc sửa dòng khi phiếu còn nháp. Khi xác nhận nhận hàng, hệ thống kiểm tra trạng thái, số lượng và đơn giá, cập nhật tồn và giá vốn, đồng thời ghi lịch sử biến động trong cùng giao dịch. Phiếu đã nhận không được xác nhận thêm lần nữa như một nghiệp vụ nhập mới.')
table('Bảng 3.8. Các nguồn biến động kho được quản lý',['Nghiệp vụ','Thời điểm ghi nhận','Nội dung kiểm soát'],[
    ('Nhập hàng','Khi xác nhận phiếu nhận hàng','Tăng tồn và cập nhật giá vốn bình quân.'),
    ('Xuất theo món','Khi gửi món theo dõi kho xuống bếp','Tính định mức, xét lượng giữ và ngăn trừ lặp.'),
    ('Hoàn do hủy món','Khi thỏa điều kiện hoàn nguyên liệu','Xét giai đoạn chế biến và dấu mốc đã hoàn.'),
    ('Kiểm kê','Khi chốt phiếu kiểm kê','So sánh tồn hệ thống với lượng thực đếm và ghi chênh lệch.'),
    ('Hao hụt','Khi ghi nhận nguyên liệu hao hụt','Lưu lượng, nguyên nhân và giá vốn tại thời điểm xử lý.'),
],[1.30,2.25,2.98])
p('Sổ biến động lưu nguyên liệu, loại giao dịch, số lượng, tồn trước, tồn sau, người thực hiện và thời điểm. Với dữ liệu minh họa, phiếu nhập ghi nhận 50 kg gạo; hai lần gửi bếp, mỗi lần hai phần với định mức 0,2 kg mỗi phần, làm giảm tổng cộng 0,8 kg. Tồn còn lại 49,2 kg được đối chiếu với màn hình kho trong Hình 3.6. Đây là dữ liệu thử để minh họa quan hệ giữa chứng từ và số dư.')

heading('3.3.8. Xây dựng chức năng quản lý nhà cung cấp')
p('Nhà cung cấp được quản lý theo tên, thông tin liên hệ, địa chỉ và trạng thái hợp tác. Phiếu nhập bắt buộc liên kết nhà cung cấp phù hợp, nhờ đó nhân viên có thể đối chiếu nguyên liệu nhận, đơn giá và chứng từ của từng đối tác. Khi thông tin liên hệ thay đổi, hồ sơ được cập nhật mà không làm mất quan hệ tới các phiếu đã phát sinh.')
p('Nhà cung cấp đã được tham chiếu trong chứng từ không bị xóa tùy ý; trạng thái ngừng hợp tác được sử dụng khi không tiếp tục giao dịch. Phạm vi cài đặt tập trung vào hồ sơ và liên kết nhập hàng, chưa bao gồm quản lý công nợ hoặc quy trình mua hàng nâng cao. Hình 3.6 thể hiện nhà cung cấp ngay trên phiếu nhập đã nhận, cùng nguyên liệu, số lượng, đơn giá và tổng giá trị chứng từ.')
plate('inventory','receipt-received','Hình 3.6. Giao diện quản lý kho và nhà cung cấp')

heading('3.3.9. Xây dựng chức năng thanh toán và hóa đơn')
p('Màn hình thanh toán sử dụng các dòng món chưa hủy và đơn giá đã lưu để tính tiền. Máy chủ xác định tổng trước giảm, ưu đãi thành viên, khuyến mãi và khoản cọc được khấu trừ khi có. Thu ngân lựa chọn phương thức hợp lệ; hệ thống kiểm tra lại quyền, trạng thái đơn và tình trạng giao dịch trực tuyến trước khi ghi nhận. Một giao dịch đang chờ kết quả không được mặc nhiên bỏ qua để thu thêm bằng phương thức khác.')
p('Các phương thức có trong cài đặt gồm thu tiền mặt, ghi nhận chuyển khoản và các luồng tích hợp thanh toán trực tuyến VNPAY, ZaloPay. Kết quả trực tuyến được xác minh và đối chiếu với giao dịch tương ứng trước khi áp dụng. Việc ghi nhận thanh toán cục bộ hoặc sử dụng cổng thử nghiệm không được xem là bằng chứng đã phát sinh giao dịch ngân hàng thật. Hình minh họa sử dụng khoản chuyển khoản được ghi nhận trong cơ sở dữ liệu kiểm thử.')
p('Hóa đơn lưu số hiệu, tổng tiền, số tiền đã thu, trạng thái và thời điểm chốt. Gửi lặp yêu cầu hoặc nhận lại thông báo của giao dịch đã xử lý không tạo thêm tác động thu tiền. Sau khi hoàn tất, giao diện thể hiện trạng thái đã thanh toán và số còn lại. Bàn chuyển sang trạng thái cần dọn theo quy trình phục vụ, không tự trở thành bàn sẵn sàng chỉ vì thu tiền xong.')
p('Các điều chỉnh sau thanh toán được thực hiện qua nghiệp vụ hoàn tiền và đối soát có trạng thái, quyền xử lý, lý do và thông tin tham chiếu. Chương trình không sửa âm thầm hóa đơn đã chốt để che khuất khoản hoàn. Trong dữ liệu minh họa, hóa đơn HD000002 có tổng 130.000 đồng, đã thu đủ và còn lại 0 đồng; kết quả này được sử dụng để đối chiếu với báo cáo cùng kỳ.')

heading('3.3.10. Xây dựng chức năng báo cáo và thống kê')
p('Trang báo cáo cho phép chọn khoảng ngày, hiển thị doanh thu, hóa đơn, giá vốn, lãi gộp, dòng tiền, món bán chạy và tình hình phục vụ. Các mốc ngày được chuyển thành khoảng đầu ngày đến đầu ngày kế tiếp theo múi giờ ứng dụng. Truy vấn tổng hợp hóa đơn được tổ chức riêng với các truy vấn dòng món và phiếu thu để hạn chế cộng trùng khi một hóa đơn có nhiều món hoặc nhiều bản ghi thanh toán.')
table('Bảng 3.9. Định nghĩa một số chỉ tiêu báo cáo',['Chỉ tiêu','Nguồn và cách xác định'],[
    ('Doanh thu hóa đơn','Tổng giá trị hóa đơn đã thanh toán, theo thời điểm chốt trong khoảng lọc.'),
    ('Doanh thu sau hoàn','Doanh thu hóa đơn trong kỳ, trừ khoản hoàn đã hoàn tất trong kỳ của hóa đơn đã thanh toán.'),
    ('Số hóa đơn','Đếm bản ghi hóa đơn đã thanh toán trong khoảng lọc, không đếm theo số dòng món.'),
    ('Giá vốn món bán','Tổng giá vốn đã lưu của dòng món không hủy thuộc hóa đơn đã thanh toán trong kỳ.'),
    ('Lãi gộp','Doanh thu sau điều chỉnh hoàn tiền trừ giá vốn món bán; chưa đồng nhất với lợi nhuận sau mọi chi phí.'),
    ('Món bán chạy','Tổng hợp số lượng và giá trị các dòng món hợp lệ thuộc hóa đơn đã thanh toán.'),
],[1.55,4.98])
p('Các chỉ tiêu được phân biệt theo thời điểm và mục đích. Số đơn phát sinh trên bảng điều khiển không đồng nghĩa số hóa đơn đã thanh toán. Tổng tiền thu cũng không mặc nhiên bằng doanh thu hóa đơn, vì có thể bao gồm cọc nhận trước hoặc khoản cần đối soát. Biểu đồ doanh thu theo ngày sử dụng thời điểm chốt hóa đơn; các khoản hoàn và chỉ tiêu sau điều chỉnh phải được đọc theo đúng định nghĩa tương ứng.')
p('Vùng dự báo số đơn được tách khỏi dữ liệu đã phát sinh, thể hiện kỳ dự báo và nguồn dữ liệu. Trong bản minh họa hiện tại, phần dự báo được gắn nhãn dữ liệu mô phỏng, không được sử dụng để khẳng định số đơn thực tế của nhà hàng. Bộ lọc của báo cáo nghiệp vụ và kỳ dự báo được trình bày riêng để người dùng không nhầm lẫn phạm vi thời gian.')
p('Chức năng xuất báo cáo tạo tệp CSV có tên chứa khoảng ngày đã chọn. Dữ liệu gồm mã hóa đơn, mã đơn, bàn, thời điểm ghi nhận, doanh thu, giá vốn, phương thức và loại bút toán; khoản hoàn được xuất thành dòng điều chỉnh tương ứng. Tệp hiện chưa có một trường riêng ghi thời điểm thực hiện xuất báo cáo. Hình 3.7 minh họa hóa đơn đã thanh toán và báo cáo được lọc trên tập dữ liệu thử có thể đối chiếu thủ công.')
plate('invoice-paid','reports','Hình 3.7. Giao diện hóa đơn và thống kê')

heading('Tài liệu tham khảo cho mục 3.3',2)
for text in [
    'Django Software Foundation. Django 5.2 documentation: Using the Django authentication system. https://docs.djangoproject.com/en/5.2/topics/auth/default/',
    'Django Software Foundation. Django 5.2 documentation: How to use sessions. https://docs.djangoproject.com/en/5.2/topics/http/sessions/',
    'Django Software Foundation. Django 5.2 documentation: Creating forms from models. https://docs.djangoproject.com/en/5.2/topics/forms/modelforms/',
    'Nguồn minh chứng triển khai: mô hình, biểu mẫu, dịch vụ và giao diện của hệ thống Cơm Quê. Ảnh minh họa chụp ngày 20/11/2026 bằng dữ liệu kiểm thử riêng; không phải dữ liệu hoạt động kinh doanh thực tế.',
]:
    para=p(text);para.alignment=WD_ALIGN_PARAGRAPH.LEFT
    para.paragraph_format.first_line_indent=Inches(0)
    para.paragraph_format.line_spacing=1.1
    for run in para.runs:run.font.size=Pt(11)

doc.core_properties.title='Mục 3.3 Xây dựng hệ thống quản lý'
doc.core_properties.subject='Nội dung báo cáo tốt nghiệp và ảnh giao diện đã cài đặt'
doc.core_properties.author=''
target=OUT/'Muc_3_3_Xay_dung_he_thong_quan_ly.docx'
doc.save(target)
assert hashlib.sha256(REFERENCE.read_bytes()).hexdigest()==reference_sha
with ZipFile(target) as archive:
    assert all(hashlib.sha256(archive.read(name)).hexdigest()==digest for name,digest in preserved.items())
assert len(doc.tables)==4 and len(doc.inline_shapes)==12
print(target)
print('Preserved reference format; four tables and twelve real UI screenshots.')
