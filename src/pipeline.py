"""تجميع خط المعالجة — التقنيع والحواجز قبل دخول المخطط، ثم التشغيل والأثر.

نقطة الدخول الوحيدة التي تلمس النص الخام: هنا يُقنَّع PII ويُعقَّم الحقن **قبل**
بناء حالة المخطط، فلا raw_text ولا PII يدخلان الحالة/الcheckpoint (نقد B3).
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from src.agents.real import RealAgents
from src.effects import FileEffects
from src.graph.build import AgentDeps, build_graph
from src.guardrails import output_guard
from src.guardrails.budget import BudgetExceeded, BudgetGuard, enforce_input_size
from src.guardrails.input_guard import sanitize_document
from src.guardrails.path_guard import safe_doc_id
from src.llm import LLMLayer
from src.observability import tracing
from src.policy_store import PolicyStore


def prepare_text(raw: str, guardrails: bool) -> tuple[str, dict]:
    """يطبّق الحواجز ويعيد (نصًا آمنًا، تقرير حواجز). مع --no-guardrails يُتخطى (للـpentest)."""
    flags = {"size_ok": True, "injection_flagged": False, "pii_masked": False}
    if not guardrails:
        return raw, flags
    try:
        enforce_input_size(raw)
    except Exception:
        tracing.GUARDRAIL_BLOCKS.labels(kind="input_size").inc()
        raise
    san = sanitize_document(raw)
    flags["injection_flagged"] = san.was_flagged
    flags["removed_lines"] = len(san.removed_lines)
    if san.was_flagged:
        tracing.GUARDRAIL_BLOCKS.labels(kind="injection").inc()
    masked = output_guard.mask_pii(san.clean_text)
    flags["pii_masked"] = masked != san.clean_text
    return masked, flags


def build_production_graph(checkpointer, policy_file: str | Path):
    llm = LLMLayer()
    store = PolicyStore()
    store.index_policy_file(policy_file)
    agents = RealAgents(llm, store)
    deps = AgentDeps(
        classify=agents.classify,
        extract=agents.extract,
        policy_check=agents.policy_check_with_tools,   # ReAct بأدوات حقيقية (البند 1)
        plan=agents.plan,          # مخطِّط LLM (Plan-and-Execute)
        review=agents.review,      # مراجع ناقد (Reflexion)
        effects=FileEffects(Path(__file__).parent.parent),   # أرشفة وإشعار حقيقيان
    )
    return build_graph(deps, checkpointer=checkpointer), llm


def process_document(
    graph,
    doc_id: str,
    raw_text: str,
    guardrails: bool,
    reports_dir: str | Path,
    llm=None,
    thread_id: str | None = None,
):
    """يعالج وثيقة ويكتب أثرها.

    `thread_id` منفصل عن `doc_id` عمدًا: معرّف الوثيقة يسمّي ملف الأثر، ومعرّف
    الخيط يعرّف الحالة في الcheckpointer. تشغيلتان بنفس معرّف الخيط تستأنف
    الثانية فوق الأولى فيندمج أثرهما في ملف واحد — عيب أدلة رُصد حيًا.
    """
    try:
        safe_id = safe_doc_id(doc_id)
    except Exception:
        tracing.GUARDRAIL_BLOCKS.labels(kind="path_traversal").inc()
        raise
    safe_text, flags = prepare_text(raw_text, guardrails)
    if llm is not None:
        llm.active_doc_id = safe_id   # ينسب الاستهلاك لهذه الوثيقة (تكلفة لكل وثيقة)
        # حاجز الميزانية: عدّاد جديد لكل وثيقة — يفشل بصوت عالٍ عند تجاوز الحد.
        llm.budget = BudgetGuard(max_calls=int(os.getenv("MAX_LLM_CALLS_PER_DOC", "12")))
    state_in = {"doc_id": safe_id, "masked_text": safe_text, "extract_attempts": 0, "audit_trail": []}
    thread = safe_doc_id(thread_id) if thread_id else safe_id
    cfg = {"configurable": {"thread_id": thread}}
    t0 = time.perf_counter()
    try:
        out = graph.invoke(state_in, cfg)
    except BudgetExceeded:
        tracing.GUARDRAIL_BLOCKS.labels(kind="budget").inc()
        raise
    tracing.observe_doc_latency((time.perf_counter() - t0) * 1000)
    status = out.get("final_status", "awaiting_approval")
    tracing.DOCS_PROCESSED.labels(final_status=status).inc()
    for e in out.get("audit_trail", []):
        tracing.NODE_RUNS.labels(node=e.node).inc()
    tracing.write_trace(reports_dir, safe_id, out.get("audit_trail", []))
    return {
        "doc_id": safe_id,
        "thread_id": thread,
        "final_status": status,
        "guardrails": flags,
        "tool_calls": out.get("tool_calls", 0),
        "decision_source": out.get("decision_source", "n/a"),
    }
