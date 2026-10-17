"""Entry point that runs every check on a PDF statement."""

import pdfplumber
from pypdf import PdfReader

from . import content_checks, excel_checks, pdf_checks
from .models import Report


def analyze(path):
    report = Report(path=str(path))
    with open(path, "rb") as fh:
        raw = fh.read()

    suffix = str(path).lower().rsplit(".", 1)[-1]
    if raw.startswith(b"PK\x03\x04") and suffix in ("xlsx", "xlsm"):
        excel_checks.check_xlsx(path, report)
        return report
    if raw.startswith(b"\xd0\xcf\x11\xe0"):
        report.add("structure", "info",
                   "File Excel đời cũ (.xls) chưa được hỗ trợ ở bản Python - hãy dùng bản trình duyệt "
                   "(browser/soi-sao-ke.html). Đừng mở rồi lưu lại thành .xlsx vì sẽ xoá dấu vết gốc.")
        return report
    if suffix in ("csv", "txt"):
        excel_checks.check_csv(path, report)
        return report
    if not raw.startswith(b"%PDF"):
        report.add("structure", "high", "File không phải PDF hay Excel hợp lệ")
        return report

    try:
        reader = PdfReader(path)
        if reader.is_encrypted and not reader.decrypt(""):
            report.add("structure", "medium", "File được mã hoá bằng mật khẩu - không thể phân tích đầy đủ")
            return report
    except Exception as exc:
        report.add("structure", "high", f"Cấu trúc PDF bị lỗi, không đọc được: {exc}")
        return report

    pdf_checks.check_metadata(reader, raw, report)
    pdf_checks.check_revisions(raw, report)
    pdf_checks.check_signatures(reader, report)
    pdf_checks.check_annotations(reader, report)

    with pdfplumber.open(path) as pdf:
        pdf_checks.check_fonts(pdf, report)
        pdf_checks.check_overlapping_text(pdf, report)
        lines = []
        for page in pdf.pages:
            lines.extend((page.extract_text() or "").splitlines())
        if content_checks.check_text_layer(lines, len(pdf.pages), report):
            content_checks.check_transactions(lines, report)

    return report
