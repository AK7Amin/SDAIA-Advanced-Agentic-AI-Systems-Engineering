"""Helper: يستأنف مخططًا محفوظًا في عملية بايثون **جديدة كليًا** (نقد B2).

الاستخدام: python resume_in_new_process.py <sqlite_db> <thread_id> <approve|reject>
يعيد بناء نفس المخطط الموهوم مربوطًا بقاعدة الcheckpoint، ويستأنف بـ
Command(resume=...)، ويطبع final_status. هذا هو الدليل الذي يطلبه نمط الrubric:
الاستئناف عبر حدود العملية، لا داخل نفس العملية فقط.
"""
import sqlite3
import sys
from pathlib import Path

# حقن جذر المشروع قبل استيراد src (لازم لفك تسلسل AuditEvent عبر مسار الاستيراد).
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.checkpointing import make_sqlite_saver  # noqa: E402
from langgraph.types import Command  # noqa: E402

from src.graph.build import AgentDeps, build_graph  # noqa: E402
from src.schemas import (  # noqa: E402
    Classification,
    DocType,
    ExecutionPlan,
    ExtractedFields,
    PolicyVerdict,
    ReviewAction,
    ReviewVerdict,
    Verdict,
)


def _stub_deps():
    return AgentDeps(
        classify=lambda _t: Classification(doc_type=DocType.INVOICE, confidence=0.9, rationale="stub"),
        extract=lambda _t, _a: ExtractedFields(party="مورد", amount_sar=95000, signed_date="2026-09-15"),
        policy_check=lambda _f, _c="": PolicyVerdict(
            verdict=Verdict.VIOLATION, cited_policy_id="POL-003", reason="stub"
        ),
        plan=lambda _c, _t: ExecutionPlan(
            skip_extraction=False, steps=["استخراج الحقول", "تدقيق السياسات"], rationale="stub"
        ),
        review=lambda _f, _v: ReviewVerdict(action=ReviewAction.CONFIRM, critique="stub"),
    )


def main() -> int:
    db, thread_id, decision = sys.argv[1], sys.argv[2], sys.argv[3]
    saver = make_sqlite_saver(db)
    graph = build_graph(_stub_deps(), checkpointer=saver)
    cfg = {"configurable": {"thread_id": thread_id}}
    out = graph.invoke(Command(resume=decision), cfg)
    print(out.get("final_status", "UNKNOWN"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
