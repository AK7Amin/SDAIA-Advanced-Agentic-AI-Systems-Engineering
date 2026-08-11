"""خدمة FastAPI — تحوّط «خدمة قابلة للنشر» (نقد C6) + endpoint المقاييس.

POST /process يعالج وثيقة واحدة عبر خط المعالجة نفسه. GET /metrics يصدّر
عدادات Prometheus. GET /healthz فحص حياة.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel
from starlette.responses import Response

from langgraph.checkpoint.memory import InMemorySaver

from src.pipeline import build_production_graph, process_document

ROOT = Path(__file__).parent.parent
app = FastAPI(title="Document Lifecycle Agent")
_GRAPH = None


def _graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH, _ = build_production_graph(InMemorySaver(), ROOT / "policies" / "procurement_policy.md")
    return _GRAPH


class DocIn(BaseModel):
    doc_id: str
    text: str
    guardrails: bool = True


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.post("/process")
def process(doc: DocIn):
    return process_document(_graph(), doc.doc_id, doc.text, doc.guardrails, ROOT / "reports" / "generated")


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
