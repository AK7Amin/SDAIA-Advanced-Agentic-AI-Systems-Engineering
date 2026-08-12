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
    Verdict,
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


_POLICY_ID_RE = re.compile(r"POL-\d+")


class RealAgents:
    def __init__(self, llm: LLMLayer, store: PolicyStore, registry=None):
        self.llm = llm
        self.store = store
        # سجل الأدوات التي يقررها الوكيل بنفسه (البند 1: Tool Use).
        from src.tools import build_default_registry

        self.registry = registry or build_default_registry(store)

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

    def validate_citation(self, verdict: PolicyVerdict) -> PolicyVerdict:
        """**تحقق من المخرجات**: لا يُقبل استشهاد بسياسة لا وجود لها.

        النموذج قد يخترع `POL-999`. حكم مبني على سياسة موهومة أسوأ من حكم غير
        حاسم، فيُخفَّض إلى `uncertain` ويُذكر السبب — فيلتقطه المراجع الناقد
        أو يُصعَّد للبشر بدل أن يمر بثقة كاذبة.
        """
        cited = (verdict.cited_policy_id or "").strip()
        if not cited:
            return verdict
        referenced = set(_POLICY_ID_RE.findall(cited)) or {cited}
        unknown = referenced - self.store.known_ids()
        if not unknown:
            return verdict
        return PolicyVerdict(
            verdict=Verdict.UNCERTAIN,
            cited_policy_id=None,
            reason=(
                f"استشهاد بسياسة غير موجودة ({', '.join(sorted(unknown))}) — "
                f"خُفّض الحكم من {verdict.verdict.value}. الأصل: {verdict.reason[:120]}"
            ),
        )

    def _retrieve_policies(self, fields: ExtractedFields) -> str:
        query = f"طرف {fields.party} قيمة {fields.amount_sar} مدة {fields.duration_months}"
        policies = self.store.retrieve(query, k=3)
        return "\n---\n".join(f"{p['policy_id']}: {p['text']}" for p in policies)

    def policy_check_with_tools(self, fields: ExtractedFields, critique: str = ""):
        """تدقيق بنمط **ReAct**: النموذج يقرر استدعاء الأدوات (البند 1).

        يعيد (الحكم، أثر ReAct). عند تعثر الحلقة يسقط لمسار الاسترجاع المباشر
        حتى لا يتوقف النظام على التزام النموذج بالنسق.
        """
        from src.agents.react import ReActStep, run_react
        from src.tools import ToolCall

        note = f"\nتغذية راجعة من مراجع ناقد: {critique}" if critique else ""
        amount_line = (
            f"المبلغ في الوثيقة: {fields.amount_sar}. **يجب** أن تستعمل calculator لمقارنته "
            f"بالحد الوارد في السياسة (مثال: Action Input: {fields.amount_sar} > 100000).\n"
            if fields.amount_sar
            else ""
        )
        task = (
            f"دقّق حقول الوثيقة التالية ضد سياسات المشتريات: {fields.model_dump_json()}{note}\n"
            "**قاعدة إلزامية**: لا تُصدر حكمًا قبل قراءة السياسة فعلًا. أول فعل لك "
            "يجب أن يكون policy_lookup لجلب السياسة ذات الصلة — الحكم بلا مراجعة سياسة مرفوض.\n"
            f"{amount_line}"
            'ثم اجعل الجواب النهائي JSON فقط: {"verdict":"compliant|violation|uncertain",'
            '"cited_policy_id":"POL-XXX أو null","reason":"..."}'
        )
        call = lambda p: self.llm.invoke(p, node="policy_check")  # noqa: E731
        res = run_react(call, task, self.registry, max_steps=4)

        # النموذج المجاني غير حتمي: قد يُصدر حكمًا **دون** مراجعة أي سياسة.
        # هذا مرفوض سلوكيًا (لا حكم امتثال بلا سياسة)، فنفرض الاسترجاع ونعيد
        # السؤال بالسياسة حاضرة — والاستدعاء تنفيذ فعلي مسجَّل في الأثر.
        if res.tool_calls == 0:
            # استدعاء منظَّم يمر بنفس الموزِّع والتحقق — لا مسار جانبي.
            forced_call = ToolCall("policy_lookup", {"query": fields.model_dump_json()})
            forced = self.registry.dispatch(forced_call).output
            seeded = (
                f"{task}\n\nObservation (policy_lookup): {forced}\n"
                "بناءً على السياسة أعلاه، أكمل: استعمل calculator عند وجود مبلغ، "
                "ثم أعطِ Final Answer بصيغة JSON."
            )
            res2 = run_react(call, seeded, self.registry, max_steps=3)
            res2.steps.insert(
                0,
                ReActStep(
                    "مراجعة السياسة إلزامية قبل الحكم",
                    "policy_lookup",
                    json.dumps(forced_call.arguments, ensure_ascii=False),
                    forced,
                    forced_call,
                ),
            )
            # **صدق الإسناد**: النموذج لم يختر هذه الأداة — النظام فرضها.
            # العلم مستقل عن `decision_source` لأن مسار السقوط أدناه يكتب فوقه.
            res2.decision_source = "policy_enforced"
            res2.forced_first_call = True
            res = res2

        if res.final_answer:
            try:
                d = _parse_json(res.final_answer)
                verdict = PolicyVerdict(
                    **{k: d.get(k) for k in ("verdict", "cited_policy_id", "reason")}
                )
                return self.validate_citation(verdict), res
            except (AgentOutputError, ValueError):
                pass
        # لم يصلنا حكم صالح من حلقة الأدوات ← مسار الاسترجاع المباشر.
        res.decision_source = "fallback_direct_retrieval"
        return self.policy_check(fields, critique), res

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
        return self.validate_citation(
            PolicyVerdict(**{k: d.get(k) for k in ("verdict", "cited_policy_id", "reason")})
        )

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
