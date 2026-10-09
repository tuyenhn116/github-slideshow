"""Command line: python -m statement_checker <file.pdf> [...] [--json]"""

import argparse
import json
import sys

from .analyzer import analyze
from .models import SEVERITY_LABELS

ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def print_report(report, verbose):
    print("=" * 72)
    print(f"File: {report.path}")
    print(f"Điểm rủi ro: {report.score}/100  ->  Mức độ: {report.verdict}")
    print("-" * 72)
    for f in sorted(report.findings, key=lambda f: ORDER[f.severity]):
        if f.severity == "info" and not verbose:
            continue
        print(f"[{SEVERITY_LABELS[f.severity]}] {f.message}")
        for d in f.details:
            print(f"    - {d}")
    print()


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="statement_checker",
        description="Phát hiện dấu hiệu sao kê ngân hàng (PDF) bị chỉnh sửa / làm giả.")
    parser.add_argument("files", nargs="+", help="Đường dẫn file PDF sao kê")
    parser.add_argument("--json", action="store_true", help="Xuất kết quả dạng JSON")
    parser.add_argument("-v", "--verbose", action="store_true", help="Hiện cả mục thông tin")
    args = parser.parse_args(argv)

    reports = [analyze(path) for path in args.files]
    if args.json:
        print(json.dumps([r.to_dict() for r in reports], ensure_ascii=False, indent=2, default=str))
    else:
        for r in reports:
            print_report(r, args.verbose)
        print("Lưu ý: kết quả chỉ là cảnh báo dựa trên dấu hiệu kỹ thuật, không phải kết luận pháp lý.\n"
              "Luôn xác minh trực tiếp với ngân hàng phát hành khi có nghi ngờ.")
    return 2 if any(r.score >= 50 for r in reports) else 0


if __name__ == "__main__":
    sys.exit(main())
