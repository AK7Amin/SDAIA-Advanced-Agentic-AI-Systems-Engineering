"""الوكلاء الحقيقيون — يغلّفون نداء النموذج ويعيدون أنواعًا محددة (typed).

كل وكيل: يبني المطالبة (نص الوثيقة مغلّف كبيانات)، ينادي النموذج، يحلل JSON
إلى عقد Pydantic. فشل التحليل يرفع استثناءً محددًا (يُلتقط في حاجز المخرجات).
"""
from __future__ import annotations

import json
import re

from src.agents.prompts import CLASSIFIER, EXTRACTOR, PLANNER, POLICY_CHECKER, REVIEWER
from src.guardrails.input_guard import wrap_untrusted
from src.llm import LLMLayer
from src.policy_store import PolicyStore
from src.schemas import (
    Classification,
    ExecutionPlan,
    ExtractedFields,
    PolicyVerdict,
    ReviewVerdict,
)


class AgentOutputError(ValueError):
    """مخرج نموذج غير قابل للتحليل إلى العقد المطلوب."""


def _parse_json(raw: str) -> dict:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        raise AgentOutputError(f"لا JSON في المخرج: {raw[:120]!r}")
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError as e:
        raise AgentOutputError(f"JSON غير صالح: {e}") from None


class RealAgents:
    def __init__(self, llm: LLMLayer, store: PolicyStore):
        self.llm = llm
        self.store = store

    def classify(self, masked_text: str) -> Classification:
        out = self.llm.invoke(CLASSIFIER.format(doc=wrap_untrusted(masked_text)), node="classify")
        d = _parse_json(out)
        return Classification(**d)

    def extract(self, masked_text: str, attempt: int) -> ExtractedFields:
        hint = "" if attempt == 0 else "تنبيه: المحاولة السابقة نقصها حقول أساسية؛ ابحث بدقة عن الطرف والقيمة والتاريخ."
        out = self.llm.invoke(
            EXTRACTOR.format(doc=wrap_untrusted(masked_text), hint=hint), node="extract"
        )
        d = _parse_json(out)
        return ExtractedFields(**{k: d.get(k) for k in ("party", "amount_sar", "duration_months", "signed_date")})

    def plan(self, classification: Classification, masked_text: str) -> ExecutionPlan:
        """وكيل التخطيط: النموذج يقرر خطة المعالجة (نمط Plan-and-Execute)."""
        out = self.llm.invoke(
            PLANNER.format(
                doc_type=classification.doc_type.value,
                doc=wrap_untrusted(masked_text[:1200]),
            ),
            node="plan_route",
        )
        d = _parse_json(out)
        steps = d.get("steps") or ["تدقيق السياسات"]
        return ExecutionPlan(
            skip_extraction=bool(d.get("skip_extraction", False)),
            steps=steps,
            rationale=str(d.get("rationale", "")),
        )

    def _retrieve_policies(self, fields: ExtractedFields) -> str:
        query = f"طرف {fields.party} قيمة {fields.amount_sar} مدة {fields.duration_months}"
        policies = self.store.retrieve(query, k=3)
        return "\n---\n".join(f"{p['policy_id']}: {p['text']}" for p in policies)

    def policy_check(self, fields: ExtractedFields, critique: str = "") -> PolicyVerdict:
        pol_text = self._retrieve_policies(fields)
        note = f"\nتغذية راجعة من المراجع الناقد، خذها بالحسبان: {critique}" if critique else ""
        out = self.llm.invoke(
            POLICY_CHECKER.format(
                fields=fields.model_dump_json(), policies=pol_text, critique=note
            ),
            node="policy_check",
        )
        d = _parse_json(out)
        return PolicyVerdict(**{k: d.get(k) for k in ("verdict", "cited_policy_id", "reason")})

    def review(self, fields: ExtractedFields, verdict: PolicyVerdict) -> ReviewVerdict:
        """وكيل المراجعة الناقد: المقيّم+العاكس في حلقة Reflexion."""
        out = self.llm.invoke(
            REVIEWER.format(
                fields=fields.model_dump_json(),
                verdict=verdict.model_dump_json(),
                policies=self._retrieve_policies(fields),
            ),
            node="reflect",
        )
        d = _parse_json(out)
        return ReviewVerdict(action=d.get("action", "confirm"), critique=str(d.get("critique", "")))
