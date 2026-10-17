import io
import os
import tempfile
import unittest

from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from statement_checker import analyze
from statement_checker.content_checks import parse_amount

ROWS = [
    ("02/01/2024", "Luong thang 12", "15.000.000", "", "25.000.000"),
    ("05/01/2024", "Chuyen tien nha", "", "4.500.000", "20.500.000"),
    ("10/01/2024", "Thanh toan dien", "", "750.000", "19.750.000"),
    ("15/01/2024", "Nhan tien ban hang", "3.250.000", "", "23.000.000"),
]


def build_statement(path, rows=ROWS, overlay=None, closing="23.000.000"):
    c = canvas.Canvas(path, pagesize=A4)
    c.setCreator("CoreBanking Statement Engine")
    c.setFont("Helvetica", 10)
    y = 800
    c.drawString(40, y, "SAO KE TAI KHOAN - So TK 0123456789")
    y -= 20
    c.drawString(40, y, "So du dau ky: 10.000.000")
    y -= 20
    for d, desc, credit, debit, bal in rows:
        c.drawString(40, y, d)
        c.drawString(120, y, desc)
        c.drawRightString(360, y, credit)
        c.drawRightString(450, y, debit)
        c.drawRightString(550, y, bal)
        y -= 16
    c.drawString(40, y - 10, f"So du cuoi ky: {closing}")
    if overlay:
        overlay(c)
    c.save()


def severities(report, check=None):
    return [f.severity for f in report.findings if check is None or f.check == check]


class CheckerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def path(self, name):
        return os.path.join(self.tmp.name, name)

    def test_parse_amount(self):
        self.assertEqual(parse_amount("1.500.000"), 1500000)
        self.assertEqual(parse_amount("1,500,000.50"), 1500000.50)
        self.assertEqual(parse_amount("1.500.000,50"), 1500000.50)
        self.assertEqual(parse_amount("-200,000"), -200000)

    def test_genuine_statement_is_low_risk(self):
        p = self.path("genuine.pdf")
        build_statement(p)
        report = analyze(p)
        self.assertLess(report.score, 20, [f.message for f in report.findings])
        self.assertTrue(any("khớp với toàn bộ" in f.message for f in report.findings))

    def test_edited_balance_detected(self):
        rows = list(ROWS)
        rows[2] = ("10/01/2024", "Thanh toan dien", "", "750.000", "91.750.000")
        p = self.path("edited.pdf")
        build_statement(p, rows=rows)
        report = analyze(p)
        self.assertIn("critical", severities(report, "content"))
        self.assertGreaterEqual(report.score, 50)

    def test_closing_balance_mismatch(self):
        p = self.path("closing.pdf")
        build_statement(p, closing="230.000.000")
        report = analyze(p)
        self.assertTrue(any("cuối kỳ" in f.message for f in report.findings))

    def test_invalid_date(self):
        rows = list(ROWS)
        rows[1] = ("31/02/2024",) + rows[1][1:]
        p = self.path("date.pdf")
        build_statement(p, rows=rows)
        report = analyze(p)
        self.assertTrue(any("không tồn tại" in f.message for f in report.findings))

    def test_incremental_save_and_editor_metadata(self):
        p = self.path("base.pdf")
        build_statement(p)
        writer = PdfWriter(p, incremental=True)
        writer.add_metadata({"/Producer": "iLovePDF", "/ModDate": "D:20240301120000+07'00'"})
        out = self.path("resaved.pdf")
        with open(out, "wb") as fh:
            writer.write(fh)
        report = analyze(out)
        self.assertIn("high", severities(report, "structure"))
        self.assertIn("high", severities(report, "metadata"))
        self.assertGreaterEqual(report.score, 50)

    def test_overlay_text_detected(self):
        def overlay(c):
            c.setFillColorRGB(1, 1, 1)
            c.rect(498, 757, 54, 12, fill=1, stroke=0)
            c.setFillColorRGB(0, 0, 0)
            c.setFont("Courier", 10)
            c.drawRightString(550, 760, "99.000.000")

        p = self.path("overlay.pdf")
        build_statement(p, overlay=overlay)
        report = analyze(p)
        self.assertIn("high", severities(report, "overlay"))
        self.assertIn("medium", severities(report, "fonts"))

    def test_scanned_image_only(self):
        p = self.path("scan.pdf")
        c = canvas.Canvas(p)
        c.rect(50, 50, 400, 600, fill=1)
        c.save()
        report = analyze(p)
        self.assertIn("medium", severities(report, "content"))

    def test_not_a_pdf(self):
        p = self.path("fake.pdf")
        with open(p, "wb") as fh:
            fh.write(b"hello")
        self.assertEqual(analyze(p).score, 30)


if __name__ == "__main__":
    unittest.main()
