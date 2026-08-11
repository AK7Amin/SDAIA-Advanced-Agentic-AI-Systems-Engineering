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

from src.schemas import (
    AuditEvent,
    Classification,
    DocType,
    ExtractedFields,
    PolicyVerdict,
    Verdict,
)
from src.state import DocState

MAX_EXTRACT_ATTEMPTS = 2


@dataclass
class AgentDeps:
    classify: Callable[[str], Classification]
    extract: Callable[[str, int], ExtractedFields]
    policy_check: Callable[[ExtractedFields], PolicyVerdict]


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
        # عقدة تخطيط: القرار يغيّر التدفق (الخطابات تتخطى الاستخراج).
        dt = state["classification"].doc_type
        plan = "skip_extract" if dt == DocType.LETTER else "full"
        return {"audit_trail": [_audit(state, "plan_route", f"خطة={plan} لنوع {dt.value}")]}

    def extract(state: DocState):
        attempt = state.get("extract_attempts", 0)
        fields = deps.extract(state["masked_text"], attempt)
        return {
            "extraction": fields,
            "extract_attempts": attempt + 1,
            "audit_trail": [_audit(state, "extract", f"محاولة {attempt + 1}؛ ناقص={fields.missing_fields()}")],
        }

    def policy_check(state: DocState):
        v = deps.policy_check(state.get("extraction") or ExtractedFields())
        return {"policy_verdict": v, "audit_trail": [_audit(state, "policy_check", f"حكم={v.verdict.value} سياسة={v.cited_policy_id}")]}

    def escalate(state: DocState):
        # تكتب الحالة وترجع طبيعيًا (interrupt في العقدة التالية — نقد B1).
        return {"final_status": "awaiting_approval", "audit_trail": [_audit(state, "escalate", "صُعّدت لموافقة بشرية")]}

    def human_gate(state: DocState):
        decision = interrupt({"doc_id": state.get("doc_id"), "ask": "approve|reject"})
        # كل التأثيرات بعد interrupt (تتفادى التكرار عند الاستئناف).
        if decision == "approve":
            return {"human_decision": "approve", "audit_trail": [_audit(state, "human_gate", "وافق المراجع")]}
        return {"human_decision": "reject", "audit_trail": [_audit(state, "human_gate", "رفض المراجع")]}

    def archive(state: DocState):
        return {"final_status": "archived", "audit_trail": [_audit(state, "archive", "أُرشفت الوثيقة")]}

    def reject(state: DocState):
        return {"final_status": "rejected", "audit_trail": [_audit(state, "reject", "رُفضت الوثيقة")]}

    def notify(state: DocState):
        return {"audit_trail": [_audit(state, "notify", f"أُشعر بالحالة {state.get('final_status')}")]}

    for name, fn in [
        ("ingest", ingest), ("classify", classify), ("quarantine", quarantine),
        ("plan_route", plan_route), ("extract", extract), ("policy_check", policy_check),
        ("escalate", escalate), ("human_gate", human_gate), ("archive", archive),
        ("reject", reject), ("notify", notify),
    ]:
        g.add_node(name, fn)

    # ---- الحواف الشرطية ----
    def after_classify(state: DocState) -> str:
        return "quarantine" if state["classification"].doc_type == DocType.UNKNOWN else "plan_route"

    def after_plan(state: DocState) -> str:
        # plan_route يغيّر التدفق: الخطاب يتخطى الاستخراج مباشرة للتدقيق.
        return "policy_check" if state["classification"].doc_type == DocType.LETTER else "extract"

    def after_extract(state: DocState) -> str:
        fields = state.get("extraction")
        if fields and fields.is_complete():
            return "policy_check"
        if state.get("extract_attempts", 0) >= MAX_EXTRACT_ATTEMPTS:
            return "escalate"          # الحلقة محدودة — لا لانهاية
        return "extract"               # الحلقة: أعد الاستخراج بتلميح

    def after_policy(state: DocState) -> str:
        return "archive" if state["policy_verdict"].verdict == Verdict.COMPLIANT else "escalate"

    def after_human(state: DocState) -> str:
        return "archive" if state.get("human_decision") == "approve" else "reject"

    g.add_edge(START, "ingest")
    g.add_edge("ingest", "classify")
    g.add_conditional_edges("classify", after_classify, ["quarantine", "plan_route"])
    g.add_edge("quarantine", END)
    g.add_conditional_edges("plan_route", after_plan, ["extract", "policy_check"])
    g.add_conditional_edges("extract", after_extract, ["extract", "policy_check", "escalate"])
    g.add_conditional_edges("policy_check", after_policy, ["archive", "escalate"])
    g.add_edge("escalate", "human_gate")
    g.add_conditional_edges("human_gate", after_human, ["archive", "reject"])
    g.add_edge("archive", "notify")
    g.add_edge("reject", "notify")
    g.add_edge("notify", END)

    return g.compile(checkpointer=checkpointer)
