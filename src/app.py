"""خدمة FastAPI — تحوّط «خدمة قابلة للنشر» + endpoint المقاييس.

قرار أمني (ثغرة رُصدت في مراجعة): الخدمة **لا تقبل** من العميل تعطيل الحواجز.
الحواجز مفروضة دائمًا على مسار الخدمة؛ وضع `--no-guardrails` يبقى حصريًا في
واجهة سطر الأوامر المحلية لأغراض توليد دليل «قبل التحصين» في تقرير الاختراق.
"""
from __future__ import annotations

import os
import secrets
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel
from starlette.responses import Response

from src.checkpointing import make_sqlite_saver
from src.pipeline import build_production_graph, process_document

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")   # نفس عقد README: المفاتيح من .env لا من الكود
app = FastAPI(title="Document Lifecycle Agent")
_STATE: dict = {}


def _graph():
    """مخطط دائم بـSqliteSaver — تدعم الخدمة الاستئناف مثل واجهة الأوامر."""
    if "graph" not in _STATE:
        saver = make_sqlite_saver(ROOT / "checkpoints" / "api.sqlite")
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
    # معرّف خيط فريد لكل طلب: طلبان بنفس doc_id كانا يستأنفان الخيط نفسه
    # فيندمج تشغيلان في أثر واحد — وهو بالضبط ما يرفضه verify-traces.
    thread_id = f"api-{uuid.uuid4().hex[:8]}-{doc.doc_id}"
    # guardrails=True مثبتة — تمرير llm يفعّل حاجز الميزانية ونسب التكلفة للوثيقة.
    return process_document(
        graph, doc.doc_id, doc.text, True, ROOT / "reports" / "generated",
        llm=llm, thread_id=thread_id,
    )


def _require_approval_token(token: str | None) -> None:
    """بوابة الموافقة فعلٌ حسّاس: تعتمد عقدًا مخالفًا بنداء واحد.

    فلا تُفتح على الشبكة بلا اعتماد. وإن لم يُضبط `APPROVAL_API_TOKEN` تُغلق
    البوابة (503) بدل أن تعمل مكشوفة — الافتراض الآمن هو المنع لا السماح.
    """
    expected = os.getenv("APPROVAL_API_TOKEN", "")
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="بوابة الموافقة معطّلة: اضبط APPROVAL_API_TOKEN لتفعيلها",
        )
    if not token or not secrets.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="اعتماد غير صالح")


@app.post("/resume")
def resume(body: ResumeIn, x_approval_token: str | None = Header(default=None)):
    """استئناف وثيقة متوقفة عند الموافقة البشرية عبر الخدمة (يتطلب اعتمادًا)."""
    from langgraph.types import Command

    _require_approval_token(x_approval_token)
    graph, _ = _graph()
    out = graph.invoke(
        Command(resume=body.decision), {"configurable": {"thread_id": body.thread_id}}
    )
    return {"thread_id": body.thread_id, "final_status": out.get("final_status")}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
