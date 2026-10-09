# Công cụ phát hiện sao kê ngân hàng giả

Công cụ dòng lệnh phân tích file **PDF sao kê ngân hàng** và chấm điểm rủi ro
(0–100) dựa trên các dấu hiệu kỹ thuật thường gặp khi sao kê bị chỉnh sửa hoặc làm giả.

> ⚠️ Kết quả chỉ là **cảnh báo**, không phải kết luận pháp lý. Khi có nghi ngờ,
> luôn xác minh trực tiếp với ngân hàng phát hành (gọi tổng đài, yêu cầu ngân hàng
> gửi sao kê/xác nhận số dư trực tiếp).

## Cài đặt

```bash
cd tools/bank_statement_checker
pip install -r requirements.txt
```

## Sử dụng

```bash
python -m statement_checker sao_ke.pdf              # báo cáo dạng văn bản
python -m statement_checker *.pdf -v                # hiện cả mục thông tin (metadata, font...)
python -m statement_checker sao_ke.pdf --json       # xuất JSON để tích hợp hệ thống khác
```

### Giao diện web

```bash
python -m statement_checker.web                 # mở http://127.0.0.1:8000
python -m statement_checker.web --host 0.0.0.0 --port 8080   # cho máy khác trong mạng LAN truy cập
```

Kéo thả hoặc chọn một/nhiều file PDF; mỗi file hiện điểm rủi ro và danh sách dấu
hiệu theo mức độ. Server chỉ dùng thư viện chuẩn của Python (không cần Flask),
file tải lên được ghi tạm, phân tích rồi xoá ngay, tên file không được ghi log.
Giới hạn 20 MB/file. Không có đăng nhập — đừng mở ra Internet công khai khi chưa
đặt sau reverse proxy có xác thực.

Mã thoát (exit code) là `2` nếu có file ở mức rủi ro CAO (điểm ≥ 50), ngược lại `0`.

Dùng trong Python:

```python
from statement_checker import analyze
report = analyze("sao_ke.pdf")
print(report.score, report.verdict)
```

## Các kiểm tra

| Nhóm | Dấu hiệu | Mức |
|---|---|---|
| Đối soát nội dung | Số dư lũy kế không khớp `số dư trước ± số tiền giao dịch` | Rất cao |
| | Ngày không tồn tại (31/02...) | Rất cao |
| | Số dư đầu kỳ / cuối kỳ không khớp bảng giao dịch | Cao |
| | Giao dịch có ngày trong tương lai / sai thứ tự thời gian | Cao / TB |
| Metadata | Producer/Creator là phần mềm chỉnh sửa (Photoshop, iLovePDF, Smallpdf, Word, Canva...) | Cao |
| | Lịch sử XMP ghi nhận phần mềm chỉnh sửa | Cao |
| | `ModDate` khác `CreationDate`, metadata bị xoá trống | TB / Thấp |
| Cấu trúc PDF | Nhiều phiên bản lưu (incremental update – sửa sau khi xuất) | Cao |
| | Annotation dạng FreeText/Square/Stamp/ô nhập đè lên trang | Cao |
| Font & bố cục | Chữ bị viết đè lên chữ khác (che số cũ, gõ số mới) | Cao |
| | Font hiếm chỉ dùng cho vài chữ số | TB |
| | Cùng một font được nhúng nhiều subset khác nhau | TB |
| Khác | File là ảnh scan, không có lớp văn bản | TB |
| | File có chữ ký số → nhắc kiểm tra chữ ký trong Adobe Reader | Thông tin |

Điểm: Rất cao = 50, Cao = 30, Trung bình = 15, Thấp = 5 (tối đa 100).
Kết luận: `< 20` THẤP, `20–49` TRUNG BÌNH, `≥ 50` CAO.

Bộ đối soát số dư nhận diện dòng giao dịch là dòng có ngày (`dd/mm/yyyy`,
`yyyy-mm-dd`...) và ít nhất hai số tiền (định dạng `1.500.000`, `1,500,000.00`,
`1.500.000,50`); số cuối dòng được coi là số dư. Sao kê xếp mới-nhất-trước cũng
được hỗ trợ. Nếu bố cục bảng quá khác thường khiến phần lớn dòng không đối soát
được, công cụ chỉ báo "cần kiểm tra thủ công" thay vì kết luận giả mạo.

## Giới hạn

- File ảnh (JPG/PNG) hoặc PDF scan không đối soát được tự động.
- Kẻ làm giả có thể tạo lại toàn bộ PDF bằng công cụ "sạch" với số liệu khớp nhau;
  khi đó chỉ xác minh với ngân hàng mới phát hiện được.
- Chữ ký số chỉ được phát hiện, không được xác thực.

## Kiểm thử

```bash
python -m unittest discover -s tests -t .
```

Bộ test tự sinh các sao kê mẫu (thật, sửa số dư, sửa ngày, lưu lại bằng iLovePDF,
viết đè số tiền, ảnh scan) bằng `reportlab`.
