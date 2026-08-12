"""بناء مخطط الحالة — العقد والحواف الشرطية وحلقة الاستخراج والتصعيد المفصول.

المنسق = المخطط نفسه + عقد التوجيه الشرطي (تقارير مباشرة، لا telephone game).
كل قرار تحكم يعتمد مخرج وكيل (typed) لا الكود — هذا ما يجعله نظامًا وكيليًا
لا أنبوبًا خطيًا (بند rubric 1). `plan_route` **يغيّر التدفق فعلًا**: الخطابات
تتخطى الاستخراج مباشرة إلى التدقيق.

`deps` يجمع دوال الوكلاء الثلاث (classify/extract/policy_check) — في الإنتاج
تغلّف نداء النموذج، وفي الاختبار تُحقن كـstubs حتمية.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

# ملاحظة: langgraph 1.x يطبع تحذير deprecation عند فك تسلسل أنواع Pydantic
# الخاصة بنا من الcheckpoint (يعمل صحيحًا — أُثبت باختبار الاستئناف). واجهة
# قائمة السماح خاصة private وتتغير بين الإصدارات، فلا نعتمد عليها؛ التحذير
# غير ضار ولا يؤثر على التشغيل أو التقييم.

from src.effects import NullEffects
from src.schemas import (
    AuditEvent,
    Classification,
    DocType,
    ExecutionPlan,
    ExtractedFields,
    PolicyVerdict,
    ReviewAction,
    ReviewVerdict,
    Verdict,
)
from src.state import DocState

MAX_EXTRACT_ATTEMPTS = 2


MAX_REFLECT_ATTEMPTS = 1


@dataclass
class AgentDeps:
    classify: Callable[[str], Classification]
    extract: Callable[[str, int], ExtractedFields]
    policy_check: Callable[..., PolicyVerdict]
    plan: Callable[[Classification, str], ExecutionPlan]
    review: Callable[[ExtractedFields, PolicyVerdict], ReviewVerdict]
    #: منفّذ الآثار الحقيقية (أرشفة + إشعار). NullEffects في الاختبارات.
    effects: object = None


def _audit(state: DocState, node: str, summary: str, cost_usd: float = 0.0, latency_ms: int = 0) -> AuditEvent:
    trail = state.get("audit_trail", [])
    prev = trail[-1].digest() if trail else ""
    return AuditEvent(node=node, summary=summary, cost_usd=cost_usd, latency_ms=latency_ms, prev_hash=prev)


def build_graph(deps: AgentDeps, checkpointer=None):
    if checkpointer is None:
        checkpointer = InMemorySaver()
    g = StateGraph(DocState)

    # ---- العقد (كل عقدة = وكيل/خطوة، تكتب حدث تدقيق مسلسل) ----
    def ingest(state: DocState):
        return {"audit_trail": [_audit(state, "ingest", f"استُلمت الوثيقة {state.get('doc_id')}")]}

    def classify(state: DocState):
        c = deps.classify(state["masked_text"])
        return {"classification": c, "audit_trail": [_audit(state, "classify", f"النوع={c.doc_type.value} ثقة={c.confidence}")]}

    def quarantine(state: DocState):
        return {"final_status": "quarantined", "audit_trail": [_audit(state, "quarantine", "نوع غير معروف — حُجرت")]}

    def plan_route(state: DocState):
        """وكيل التخطيط: **النموذج** يولّد خطة typed تغيّر تدفق التحكم."""
        plan = deps.plan(state["classification"], state.get("masked_text", ""))
        return {
            "plan": plan,
            "audit_trail": [
                _audit(
                    state,
                    "plan_route",
                    f"خطة={'skip_extract' if plan.skip_extraction else 'full'} "
                    f"({len(plan.steps)} خطوات): {plan.rationale[:60]}",
                )
            ],
        }

    def extract(state: DocState):
        attempt = state.get("extract_attempts", 0)
        fields = deps.extract(state["masked_text"], attempt)
        return {
            "extraction": fields,
            "extract_attempts": attempt + 1,
            "audit_trail": [_audit(state, "extract", f"محاولة {attempt + 1}؛ ناقص={fields.missing_fields()}")],
        }

    def policy_check(state: DocState):
        # الممثل Actor في حلقة Reflexion — يستقبل نقد المراجع إن وُجد.
        out = deps.policy_check(state.get("extraction") or ExtractedFields(), state.get("critique", ""))
        # قد يعيد المدقق (حكمًا، أثر ReAct) حين يعمل بالأدوات.
        react = None
        v = out
        if isinstance(out, tuple):
            v, react = out
        summary = f"حكم={v.verdict.value} سياسة={v.cited_policy_id}"
        events = [_audit(state, "policy_check", summary)]
        if react is not None:
            # أثر استدعاء الأدوات — دليل البند 1 داخل سجل التدقيق نفسه.
            for step in react.steps:
                if step.action:
                    events.append(
                        _audit(
                            state,
                            "tool_call",
                            f"{step.action}({step.action_input[:40]}) → {str(step.observation)[:60]}",
                        )
                    )
        return {"policy_verdict": v, "tool_calls": react.tool_calls if react else 0, "audit_trail": events}

    def reflect(state: DocState):
        """المقيّم+العاكس Evaluator+Reflector — نمط Reflexion على الحكم غير الحاسم."""
        r = deps.review(state.get("extraction") or ExtractedFields(), state["policy_verdict"])
        return {
            "review": r,
            "critique": r.critique,
            "reflect_attempts": state.get("reflect_attempts", 0) + 1,
            "audit_trail": [
                _audit(state, "reflect", f"مراجعة={r.action.value}: {r.critique[:60]}")
            ],
        }

    def escalate(state: DocState):
        # تكتب الحالة وترجع طبيعيًا (interrupt في العقدة التالية — نقد B1).
        return {"final_status": "awaiting_approval", "audit_trail": [_audit(state, "escalate", "صُعّدت لموافقة بشرية")]}

    def human_gate(state: DocState):
        decision = interrupt({"doc_id": state.get("doc_id"), "ask": "approve|reject"})
        # كل التأثيرات بعد interrupt (تتفادى التكرار عند الاستئناف).
        if decision == "approve":
            return {"human_decision": "approve", "audit_trail": [_audit(state, "human_gate", "وافق المراجع")]}
        return {"human_decision": "reject", "audit_trail": [_audit(state, "human_gate", "رفض المراجع")]}

    effects = deps.effects or NullEffects()

    def archive(state: DocState):
        # فعل حقيقي: كتابة الوثيقة + قيد القرار في قاعدة قابلة للاستعلام.
        target = effects.archive(state.get("doc_id", "-"), {**state, "final_status": "archived"})
        return {
            "final_status": "archived",
            "audit_trail": [_audit(state, "archive", f"أُرشفت الوثيقة → {target}")],
        }

    def reject(state: DocState):
        return {"final_status": "rejected", "audit_trail": [_audit(state, "reject", "رُفضت الوثيقة")]}

    def notify(state: DocState):
        # فعل حقيقي: توليد نص الإشعار بقالب Jinja2 وكتابته.
        target = effects.notify(state.get("doc_id", "-"), state)
        return {
            "audit_trail": [
                _audit(state, "notify", f"أُشعر بالحالة {state.get('final_status')} → {target}")
            ]
        }

    for name, fn in [
        ("ingest", ingest), ("classify", classify), ("quarantine", quarantine),
        ("plan_route", plan_route), ("extract", extract), ("policy_check", policy_check),
        ("reflect", reflect), ("escalate", escalate), ("human_gate", human_gate),
        ("archive", archive), ("reject", reject), ("notify", notify),
    ]:
        g.add_node(name, fn)

    # ---- الحواف الشرطية ----
    def after_classify(state: DocState) -> str:
        return "quarantine" if state["classification"].doc_type == DocType.UNKNOWN else "plan_route"

    def after_plan(state: DocState) -> str:
        # قرار **النموذج** (خطة typed) هو ما يوجّه التدفق — لا شرط مكتوب في الكود.
        plan = state.get("plan")
        return "policy_check" if (plan and plan.skip_extraction) else "extract"

    def after_extract(state: DocState) -> str:
        fields = state.get("extraction")
        if fields and fields.is_complete():
            return "policy_check"
        if state.get("extract_attempts", 0) >= MAX_EXTRACT_ATTEMPTS:
            return "escalate"          # الحلقة محدودة — لا لانهاية
        return "extract"               # الحلقة: أعد الاستخراج بتلميح

    def after_policy(state: DocState) -> str:
        v = state["policy_verdict"].verdict
        if v == Verdict.COMPLIANT:
            return "archive"
        # حكم غير حاسم ← حلقة Reflexion مرة واحدة قبل إتعاب البشر.
        if v == Verdict.UNCERTAIN and state.get("reflect_attempts", 0) < MAX_REFLECT_ATTEMPTS:
            return "reflect"
        return "escalate"

    def after_reflect(state: DocState) -> str:
        # العاكس طلب إعادة النظر ← ارجع للممثل بالنقد؛ وإلا صعّد للبشر.
        review = state.get("review")
        return "policy_check" if (review and review.action == ReviewAction.REVISE) else "escalate"

    def after_human(state: DocState) -> str:
        return "archive" if state.get("human_decision") == "approve" else "reject"

    g.add_edge(START, "ingest")
    g.add_edge("ingest", "classify")
    g.add_conditional_edges("classify", after_classify, ["quarantine", "plan_route"])
    g.add_edge("quarantine", END)
    g.add_conditional_edges("plan_route", after_plan, ["extract", "policy_check"])
    g.add_conditional_edges("extract", after_extract, ["extract", "policy_check", "escalate"])
    g.add_conditional_edges("policy_check", after_policy, ["archive", "reflect", "escalate"])
    g.add_conditional_edges("reflect", after_reflect, ["policy_check", "escalate"])
    g.add_edge("escalate", "human_gate")
    g.add_conditional_edges("human_gate", after_human, ["archive", "reject"])
    g.add_edge("archive", "notify")
    g.add_edge("reject", "notify")
    g.add_edge("notify", END)

    return g.compile(checkpointer=checkpointer)
