"""Checks on the statement content: dates, amounts and running-balance arithmetic."""

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

DATE_RE = re.compile(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4}|\d{2})\b|\b(\d{4})-(\d{2})-(\d{2})\b")
# Amounts must carry thousands separators or a 2-digit decimal part, so that
# reference numbers and account numbers are not mistaken for money.
AMOUNT_RE = re.compile(
    r"(?<![\w.,])[-+]?(?:\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{1,2})?|\d+[.,]\d{2}|0)(?![\w]|[.,]\d)"
)

OPENING_RE = re.compile(r"(số dư đầu kỳ|so du dau ky|opening balance|balance brought forward|số dư đầu)",
                        re.IGNORECASE)
CLOSING_RE = re.compile(r"(số dư cuối kỳ|so du cuoi ky|closing balance|ending balance|số dư cuối)",
                        re.IGNORECASE)

TOLERANCE = Decimal("0.01")


def parse_amount(token):
    token = token.strip()
    sign = -1 if token.startswith("-") else 1
    token = token.lstrip("+-")
    seps = re.findall(r"[.,]", token)
    if seps:
        last = max(token.rfind("."), token.rfind(","))
        tail = token[last + 1:]
        if len(tail) in (1, 2):  # decimal separator
            integer = re.sub(r"[.,]", "", token[:last])
            token = f"{integer}.{tail}"
        else:
            token = re.sub(r"[.,]", "", token)
    try:
        return sign * Decimal(token)
    except InvalidOperation:
        return None


def parse_date(match):
    try:
        if match.group(4):
            return date(int(match.group(4)), int(match.group(5)), int(match.group(6)))
        d, m, y = int(match.group(1)), int(match.group(2)), int(match.group(3))
        if y < 100:
            y += 2000
        return date(y, m, d)
    except ValueError:
        return None


def extract_rows(lines):
    """Return transaction rows: lines containing a date and at least two amounts."""
    rows = []
    for no, line in enumerate(lines, 1):
        dmatch = DATE_RE.search(line)
        if not dmatch:
            continue
        rest = DATE_RE.sub(" ", line)
        amounts = [a for a in (parse_amount(t) for t in AMOUNT_RE.findall(rest)) if a is not None]
        if len(amounts) < 2:
            continue
        rows.append({"line": no, "text": line.strip(), "date": parse_date(dmatch),
                     "raw_date": dmatch.group(0), "amounts": amounts, "balance": amounts[-1]})
    return rows


def _balance_breaks(rows):
    breaks = []
    for prev, cur in zip(rows, rows[1:]):
        diff = abs(cur["balance"] - prev["balance"])
        if not any(abs(abs(a) - diff) <= TOLERANCE for a in cur["amounts"][:-1]):
            breaks.append((prev, cur, cur["balance"] - prev["balance"]))
    return breaks


def _find_labelled_amount(lines, pattern):
    for line in lines:
        if pattern.search(line):
            amounts = AMOUNT_RE.findall(DATE_RE.sub(" ", line))
            if amounts:
                return parse_amount(amounts[-1])
    return None


def check_text_layer(lines, page_count, report):
    chars = sum(len(l.strip()) for l in lines)
    if chars < 50 * max(1, page_count):
        report.add("content", "medium",
                   "File gần như không có lớp văn bản (ảnh chụp/scan) - không thể đối soát tự động",
                   ["Sao kê điện tử thật từ ngân hàng hầu như luôn có văn bản chọn được.",
                    "Hãy yêu cầu bản PDF gốc hoặc xác minh trực tiếp với ngân hàng."])
        return False
    return True


def check_transactions(lines, report):
    rows = extract_rows(lines)
    if len(rows) < 2:
        report.add("content", "info", "Không nhận diện được bảng giao dịch để đối soát số dư")
        return

    # Statements may list newest first; pick the order that reconciles best.
    forward, backward = _balance_breaks(rows), _balance_breaks(rows[::-1])
    breaks, ordered = (forward, rows) if len(forward) <= len(backward) else (backward, rows[::-1])

    report.add("content", "info", f"Nhận diện {len(rows)} dòng giao dịch",
               [r["text"][:100] for r in rows[:3]])

    if breaks:
        ratio = len(breaks) / (len(rows) - 1)
        details = [f"Dòng {cur['line']}: số dư {prev['balance']:,} -> {cur['balance']:,} "
                   f"(chênh {delta:,}) không khớp số tiền giao dịch nào: '{cur['text'][:80]}'"
                   for prev, cur, delta in breaks[:8]]
        if ratio > 0.7 and len(rows) >= 6:
            report.add("content", "info",
                       "Không đối soát được số dư (định dạng bảng không chuẩn) - cần kiểm tra thủ công",
                       details[:3])
        else:
            report.add("content", "critical",
                       f"Số dư lũy kế không khớp ở {len(breaks)}/{len(rows) - 1} giao dịch - "
                       "dấu hiệu số tiền hoặc số dư bị sửa", details)
    else:
        report.add("content", "info", "Số dư lũy kế khớp với toàn bộ giao dịch")

    opening = _find_labelled_amount(lines, OPENING_RE)
    if opening is not None:
        first = ordered[0]
        diff = abs(first["balance"] - opening)
        if not any(abs(abs(a) - diff) <= TOLERANCE for a in first["amounts"][:-1]):
            report.add("content", "high", "Số dư đầu kỳ không khớp với giao dịch đầu tiên",
                       [f"Đầu kỳ: {opening:,}; sau giao dịch đầu: {first['balance']:,}"])
    closing = _find_labelled_amount(lines, CLOSING_RE)
    if closing is not None and abs(closing - ordered[-1]["balance"]) > TOLERANCE:
        report.add("content", "high", "Số dư cuối kỳ không khớp với số dư giao dịch cuối cùng",
                   [f"Cuối kỳ: {closing:,}; giao dịch cuối: {ordered[-1]['balance']:,}"])

    _check_dates(rows, ordered is rows, report)


def _check_dates(rows, ascending, report):
    invalid = [r for r in rows if r["date"] is None]
    if invalid:
        report.add("content", "critical", "Có ngày giao dịch không tồn tại (ví dụ 31/02)",
                   [f"Dòng {r['line']}: {r['raw_date']}" for r in invalid[:5]])

    today = datetime.now().date()
    future = [r for r in rows if r["date"] and r["date"] > today]
    if future:
        report.add("content", "high", "Có giao dịch mang ngày trong tương lai",
                   [f"Dòng {r['line']}: {r['raw_date']}" for r in future[:5]])

    dated = [r for r in rows if r["date"]]
    if not ascending:
        dated = dated[::-1]
    out_of_order = [(a, b) for a, b in zip(dated, dated[1:]) if b["date"] < a["date"]]
    if out_of_order:
        report.add("content", "medium", "Ngày giao dịch không theo thứ tự thời gian",
                   [f"Dòng {a['line']} ({a['raw_date']}) -> dòng {b['line']} ({b['raw_date']})"
                    for a, b in out_of_order[:5]])
