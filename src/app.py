"""خدمة FastAPI — تحوّط «خدمة قابلة للنشر» + endpoint المقاييس.

قرار أمني (ثغرة رُصدت في مراجعة): الخدمة **لا تقبل** من العميل تعطيل الحواجز.
الحواجز مفروضة دائمًا على مسار الخدمة؛ وضع `--no-guardrails` يبقى حصريًا في
واجهة سطر الأوامر المحلية لأغراض توليد دليل «قبل التحصين» في تقرير الاختراق.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi import FastAPI
from langgraph.checkpoint.sqlite import SqliteSaver
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel
from starlette.responses import Response

from src.pipeline import build_production_graph, process_document

ROOT = Path(__file__).parent.parent
app = FastAPI(title="Document Lifecycle Agent")
_STATE: dict = {}


def _graph():
    """مخطط دائم بـSqliteSaver — تدعم الخدمة الاستئناف مثل واجهة الأوامر."""
    if "graph" not in _STATE:
        ck = ROOT / "checkpoints"
        ck.mkdir(parents=True, exist_ok=True)
        saver = SqliteSaver(sqlite3.connect(str(ck / "api.sqlite"), check_same_thread=False))
        graph, llm = build_production_graph(saver, ROOT / "policies" / "procurement_policy.md")
        _STATE["graph"], _STATE["llm"] = graph, llm
    return _STATE["graph"], _STATE["llm"]


class DocIn(BaseModel):
    doc_id: str
    text: str
    # لا حقل guardrails هنا عمدًا — لا يعطّلها العميل.


class ResumeIn(BaseModel):
    thread_id: str
    decision: str  # approve | reject


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.post("/process")
def process(doc: DocIn):
    graph, llm = _graph()
    # guardrails=True مثبتة — تمرير llm يفعّل حاجز الميزانية ونسب التكلفة للوثيقة.
    return process_document(
        graph, doc.doc_id, doc.text, True, ROOT / "reports" / "generated", llm=llm
    )


@app.post("/resume")
def resume(body: ResumeIn):
    """استئناف وثيقة متوقفة عند الموافقة البشرية عبر الخدمة."""
    from langgraph.types import Command

    graph, _ = _graph()
    out = graph.invoke(
        Command(resume=body.decision), {"configurable": {"thread_id": body.thread_id}}
    )
    return {"thread_id": body.thread_id, "final_status": out.get("final_status")}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
