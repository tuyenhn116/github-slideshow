"""Checks on the PDF file itself: metadata, revision history, fonts, annotations."""

import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

# Software that banks' statement generators never use, but that people use to edit PDFs.
EDITOR_SIGNATURES = [
    "photoshop", "illustrator", "gimp", "canva", "ilovepdf", "smallpdf", "sejda",
    "pdfescape", "pdf-xchange", "foxit phantompdf", "foxit pdf editor", "nitro",
    "pdfelement", "wondershare", "inkscape", "libreoffice", "openoffice",
    "microsoft word", "microsoft® word", "microsoft excel", "microsoft® excel",
    "wps", "pdffiller", "docfly", "pdf candy", "soda pdf", "abbyy finereader",
    "acrobat pro", "adobe acrobat", "pdf24", "paint", "pixlr", "fotor",
]

PDF_DATE_RE = re.compile(
    r"D?:?(\d{4})(\d{2})?(\d{2})?(\d{2})?(\d{2})?(\d{2})?([Zz+\-])?(\d{2})?'?(\d{2})?'?"
)


def parse_pdf_date(value):
    if not value:
        return None
    m = PDF_DATE_RE.match(str(value).strip())
    if not m:
        return None
    year, month, day, hour, minute, second, sign, tzh, tzm = m.groups()
    try:
        dt = datetime(int(year), int(month or 1), int(day or 1),
                      int(hour or 0), int(minute or 0), int(second or 0))
    except ValueError:
        return None
    offset = timedelta(0)
    if sign in ("+", "-") and tzh:
        offset = timedelta(hours=int(tzh), minutes=int(tzm or 0))
        if sign == "-":
            offset = -offset
    return dt.replace(tzinfo=timezone(offset))


def _find_editors(text):
    text = (text or "").lower()
    return [sig for sig in EDITOR_SIGNATURES if sig in text]


def check_metadata(reader, raw, report):
    info = reader.metadata or {}
    producer = str(info.get("/Producer", "") or "")
    creator = str(info.get("/Creator", "") or "")
    created = parse_pdf_date(info.get("/CreationDate"))
    modified = parse_pdf_date(info.get("/ModDate"))

    report.add("metadata", "info", "Thông tin metadata", [
        f"Producer: {producer or '(trống)'}",
        f"Creator: {creator or '(trống)'}",
        f"CreationDate: {created or '(trống)'}",
        f"ModDate: {modified or '(trống)'}",
    ])

    if not producer and not creator:
        report.add("metadata", "low",
                   "Metadata Producer/Creator bị xoá trống - có thể đã bị làm sạch để che dấu vết")

    editors = _find_editors(producer + " " + creator)
    if editors:
        report.add("metadata", "high",
                   "File được tạo/lưu bằng phần mềm chỉnh sửa, không phải hệ thống ngân hàng",
                   [f"Phát hiện: {', '.join(editors)}"])

    # XMP metadata keeps a history of every tool that saved the file.
    xmp_tools = set(re.findall(rb"(?:CreatorTool|softwareAgent)[\"'=>\s]*([^<\"']{2,120})", raw))
    xmp_tools = {t.decode("latin-1", "replace").strip() for t in xmp_tools}
    xmp_editors = sorted({e for t in xmp_tools for e in _find_editors(t)} - set(editors))
    if xmp_editors:
        report.add("metadata", "high",
                   "Lịch sử XMP cho thấy file từng được mở/lưu bằng phần mềm chỉnh sửa",
                   [f"Phát hiện: {', '.join(xmp_editors)}"] + sorted(xmp_tools)[:5])

    if created and modified:
        delta = modified - created
        if delta > timedelta(minutes=5):
            report.add("metadata", "medium",
                       "Ngày sửa đổi (ModDate) khác ngày tạo (CreationDate) - file đã bị lưu lại sau khi xuất",
                       [f"Chênh lệch: {delta}"])
        elif delta < timedelta(seconds=-60):
            report.add("metadata", "medium", "ModDate sớm hơn CreationDate - metadata không nhất quán")
    now = datetime.now(timezone.utc)
    for label, value in (("CreationDate", created), ("ModDate", modified)):
        if value and value > now + timedelta(days=1):
            report.add("metadata", "medium", f"{label} nằm trong tương lai: {value}")


def check_revisions(raw, report):
    """Each incremental save appends a new xref section and %%EOF marker."""
    eof_count = len(re.findall(rb"%%EOF", raw))
    linearized = b"/Linearized" in raw[:2048]
    revisions = eof_count - (1 if linearized and eof_count > 1 else 0)
    if revisions > 1:
        report.add("structure", "high",
                   f"File có {revisions} phiên bản lưu (incremental update) - nội dung đã bị sửa sau khi tạo",
                   ["Sao kê xuất trực tiếp từ ngân hàng thường chỉ có 1 phiên bản"])
    if b"/Prev" in raw and revisions <= 1 and not linearized:
        report.add("structure", "low", "Bảng xref có tham chiếu /Prev - có dấu hiệu từng được cập nhật")


def check_signatures(reader, report):
    fields = reader.get_fields() or {}
    sigs = [name for name, f in fields.items() if f.get("/FT") == "/Sig"]
    if sigs:
        report.add("signature", "info",
                   "File có chữ ký số - hãy kiểm tra tính hợp lệ của chữ ký trong Adobe Reader",
                   [f"Trường chữ ký: {', '.join(sigs)}"])


SUSPICIOUS_ANNOTS = {"/FreeText", "/Square", "/Stamp", "/Ink", "/Redact", "/Widget"}


def check_annotations(reader, report):
    found = Counter()
    for page in reader.pages:
        for annot in page.get("/Annots") or []:
            try:
                subtype = annot.get_object().get("/Subtype")
            except Exception:
                continue
            if subtype in SUSPICIOUS_ANNOTS:
                found[subtype] += 1
    if found:
        report.add("structure", "high",
                   "Có chú thích/ô nhập đè lên trang (thường dùng để che và viết đè số liệu)",
                   [f"{k}: {v}" for k, v in found.items()])


SUBSET_RE = re.compile(r"^[A-Z]{6}\+")


def check_fonts(pdf, report):
    """Look for inconsistent fonts - a common trace of editing individual numbers."""
    font_chars = Counter()
    font_samples = defaultdict(str)
    base_to_subsets = defaultdict(set)
    total = 0
    for page in pdf.pages:
        for ch in page.chars:
            name = ch.get("fontname") or "?"
            text = ch.get("text", "")
            if not text.strip():
                continue
            total += 1
            font_chars[name] += 1
            if len(font_samples[name]) < 40:
                font_samples[name] += text
            if SUBSET_RE.match(name):
                base_to_subsets[name[7:]].add(name[:6])

    if total == 0:
        return

    report.add("fonts", "info", f"Số font được dùng: {len(font_chars)}",
               [f"{n}: {c} ký tự" for n, c in font_chars.most_common(10)])

    for base, prefixes in base_to_subsets.items():
        if len(prefixes) > 1:
            report.add("fonts", "medium",
                       f"Font '{base}' được nhúng {len(prefixes)} lần với subset khác nhau - "
                       "dấu hiệu nội dung được ghép/sửa bằng công cụ khác",
                       [f"Subset: {', '.join(sorted(prefixes))}"])

    for name, count in font_chars.items():
        sample = font_samples[name]
        digits = sum(c.isdigit() for c in sample)
        if count / total < 0.1 and count <= 60 and digits >= max(3, len(sample) * 0.6):
            report.add("fonts", "medium",
                       f"Font hiếm '{name}' chỉ dùng cho {count} ký tự, chủ yếu là chữ số - "
                       "có thể số tiền/số dư đã bị sửa",
                       [f"Mẫu: {sample!r}"])

    if len(font_chars) > 8:
        report.add("fonts", "low", f"Dùng quá nhiều font ({len(font_chars)}) so với sao kê thông thường")


def check_overlapping_text(pdf, report, limit=5):
    """Text drawn on top of other text (e.g. new amount typed over a covered one)."""
    hits = []
    for pno, page in enumerate(pdf.pages, 1):
        lines = defaultdict(list)
        for c in page.chars:
            if c.get("text", "").strip():
                lines[round(c["top"] / 3)].append(c)
        for chars in lines.values():
            chars.sort(key=lambda c: c["x0"])
            for a, b in zip(chars, chars[1:]):
                overlap = min(a["x1"], b["x1"]) - max(a["x0"], b["x0"])
                narrow = min(a["x1"] - a["x0"], b["x1"] - b["x0"]) or 1
                if overlap / narrow < 0.6:
                    continue
                if a["text"] != b["text"] or a.get("fontname") != b.get("fontname"):
                    hits.append(f"Trang {pno}, toạ độ ({a['x0']:.0f}, {a['top']:.0f}): "
                                f"'{a['text']}' chồng lên '{b['text']}'")
    if hits:
        report.add("overlay", "high",
                   f"Phát hiện {len(hits)} vị trí chữ bị viết đè lên chữ khác",
                   hits[:limit])
