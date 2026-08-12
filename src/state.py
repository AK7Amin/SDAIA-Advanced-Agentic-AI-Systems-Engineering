"""حالة المخطط المشتركة — TypedDict مع reducers.

قرار أمني (نقد B3): `raw_text` **لا يدخل** الحالة المُنقَّطة. المخطط يعمل على
`masked_text` فقط، فلا PII في الcheckpoint المسلسل على القرص.
"""
from __future__ import annotations

from operator import add
from typing import Annotated, TypedDict

from src.schemas import (
    AuditEvent,
    Classification,
    ExecutionPlan,
    ExtractedFields,
    PolicyVerdict,
    ReviewVerdict,
)


class DocState(TypedDict, total=False):
    doc_id: str
    masked_text: str            # النص بعد تقنيع PII — لا raw_text هنا أبدًا
    classification: Classification
    plan: ExecutionPlan         # خطة يقررها النموذج (Plan-and-Execute)
    extraction: ExtractedFields
    extract_attempts: int
    policy_verdict: PolicyVerdict
    tool_calls: int             # عدد الأدوات التي قرر الوكيل استدعاءها
    review: ReviewVerdict       # مخرج المراجع الناقد (Reflexion)
    critique: str               # تغذية راجعة تُحقن في إعادة التدقيق
    reflect_attempts: int
    human_decision: str
    final_status: str
    audit_trail: Annotated[list[AuditEvent], add]   # reducer: يجمع لا يستبدل
