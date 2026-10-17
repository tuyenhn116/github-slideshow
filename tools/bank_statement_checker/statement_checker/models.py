"""Data structures shared by all checks."""

from dataclasses import dataclass, field, asdict
from typing import List

SEVERITY_WEIGHTS = {"critical": 50, "high": 30, "medium": 15, "low": 5, "info": 0}
SEVERITY_LABELS = {"critical": "RẤT CAO", "high": "CAO", "medium": "TRUNG BÌNH", "low": "THẤP", "info": "THÔNG TIN"}


@dataclass
class Finding:
    check: str
    severity: str  # critical | high | medium | low | info
    message: str
    details: List[str] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


@dataclass
class Report:
    path: str
    findings: List[Finding] = field(default_factory=list)

    def add(self, check, severity, message, details=None):
        self.findings.append(Finding(check, severity, message, list(details or [])))

    @property
    def score(self):
        """Risk score 0-100: the higher, the more likely the file was tampered with."""
        return min(100, sum(SEVERITY_WEIGHTS[f.severity] for f in self.findings))

    @property
    def verdict(self):
        if self.score >= 50:
            return "CAO - nhiều dấu hiệu chỉnh sửa/giả mạo"
        if self.score >= 20:
            return "TRUNG BÌNH - có dấu hiệu bất thường, cần xác minh thêm"
        return "THẤP - chưa phát hiện dấu hiệu bất thường rõ ràng"

    def to_dict(self):
        return {
            "path": self.path,
            "score": self.score,
            "verdict": self.verdict,
            "findings": [f.to_dict() for f in self.findings],
        }
