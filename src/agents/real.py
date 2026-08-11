"""الوكلاء الحقيقيون — يغلّفون نداء النموذج ويعيدون أنواعًا محددة (typed).

كل وكيل: يبني المطالبة (نص الوثيقة مغلّف كبيانات)، ينادي النموذج، يحلل JSON
إلى عقد Pydantic. فشل التحليل يرفع استثناءً محددًا (يُلتقط في حاجز المخرجات).
"""
from __future__ import annotations

import json
import re

from src.agents.prompts import CLASSIFIER, EXTRACTOR, POLICY_CHECKER
from src.guardrails.input_guard import wrap_untrusted
from src.llm import LLMLayer
from src.policy_store import PolicyStore
from src.schemas import Classification, ExtractedFields, PolicyVerdict


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

    def policy_check(self, fields: ExtractedFields) -> PolicyVerdict:
        query = f"طرف {fields.party} قيمة {fields.amount_sar} مدة {fields.duration_months}"
        policies = self.store.retrieve(query, k=3)
        pol_text = "\n---\n".join(f"{p['policy_id']}: {p['text']}" for p in policies)
        out = self.llm.invoke(
            POLICY_CHECKER.format(fields=fields.model_dump_json(), policies=pol_text), node="policy_check"
        )
        d = _parse_json(out)
        return PolicyVerdict(**{k: d.get(k) for k in ("verdict", "cited_policy_id", "reason")})
