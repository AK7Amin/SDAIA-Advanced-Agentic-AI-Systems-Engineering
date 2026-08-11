"""عقود الرسائل بين الوكلاء — typed outputs (بند rubric 2: multi-agent).

كل وكيل يرجع نوعًا محددًا هنا لا نصًا حرًا؛ هذا ما يمنع «لعبة الهاتف» ويجعل
التنسيق بين الوكلاء موثوقًا. الأنواع مبنية على Pydantic v2 (مثبتة في venv).
"""
from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DocType(str, Enum):
    """أنواع الوثائق المغلقة — مجموعة مقفلة closed set."""

    CONTRACT = "contract"
    INVOICE = "invoice"
    LETTER = "letter"
    UNKNOWN = "unknown"


class Verdict(str, Enum):
    """حكم التدقيق الثلاثي — مطابق / مخالف / مشكوك فيه."""

    COMPLIANT = "compliant"
    VIOLATION = "violation"
    UNCERTAIN = "uncertain"


class Classification(BaseModel):
    """مخرج وكيل التصنيف."""

    doc_type: DocType
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str


class ExtractedFields(BaseModel):
    """مخرج وكيل الاستخراج — الحقول الأساسية للوثيقة."""

    party: str | None = None
    amount_sar: float | None = Field(default=None, gt=0)
    duration_months: int | None = Field(default=None, gt=0)
    signed_date: str | None = None

    #: الحقول التي يُعدّ غيابها نقصًا يوقف الاعتماد الآلي (POL-004).
    REQUIRED: ClassVar[tuple[str, ...]] = ("party", "amount_sar", "signed_date")

    def missing_fields(self) -> list[str]:
        return [f for f in self.REQUIRED if getattr(self, f) in (None, "")]

    def is_complete(self) -> bool:
        return not self.missing_fields()


class PolicyVerdict(BaseModel):
    """مخرج وكيل تدقيق السياسات — الحكم مع استشهاد إلزامي عند المخالفة."""

    verdict: Verdict
    cited_policy_id: str | None = None
    reason: str

    @model_validator(mode="after")
    def _violation_must_cite(self) -> "PolicyVerdict":
        if self.verdict == Verdict.VIOLATION and not self.cited_policy_id:
            raise ValueError("المخالفة يجب أن تستشهد بمعرّف سياسة (cited_policy_id)")
        return self


class AuditEvent(BaseModel):
    """حدث تدقيق غير قابل للتعديل، مربوط بسلسلة تجزئة hash-chain.

    كل حدث يحمل `prev_hash` = تجزئة الحدث السابق، فأي تعديل بأثر رجعي يكسر
    السلسلة ويُكتشف — وهذا ما يجعل أثر التدقيق tamper-evident (نص الفكرة 1).
    """

    model_config = ConfigDict(frozen=True)

    node: str
    summary: str
    cost_usd: float = 0.0
    latency_ms: int = 0
    prev_hash: str = ""

    def digest(self) -> str:
        payload = json.dumps(
            {
                "node": self.node,
                "summary": self.summary,
                "cost_usd": self.cost_usd,
                "latency_ms": self.latency_ms,
                "prev_hash": self.prev_hash,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def verify_chain(events: list[AuditEvent]) -> bool:
    """التحقق أن سلسلة التجزئة سليمة — يُستخدم لإثبات عدم العبث."""
    prev = ""
    for e in events:
        if e.prev_hash != prev:
            return False
        prev = e.digest()
    return True
