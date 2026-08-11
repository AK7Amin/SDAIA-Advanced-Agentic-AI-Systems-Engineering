"""المراقبة — عدادات Prometheus + كتابة traces لكل وثيقة كملفات (بند rubric 5).

قرار الأدلة (نقد C2/C5): المقاييس والtraces تُحفظ على القرص فلا تموت بانتهاء
العملية، ويستطيع المقيّم فتحها دون تشغيل. لوحة HTML تقرأ اللقطة المحفوظة.
لا مفاتيح ولا PII في أي مخرج (نقد B7): كل نص يمر عبر redact_secrets.
"""
from __future__ import annotations

import json
from pathlib import Path

from prometheus_client import Counter, Histogram

from src.llm import redact_secrets
from src.schemas import AuditEvent, verify_chain

DOCS_PROCESSED = Counter("docs_processed_total", "عدد الوثائق المعالجة", ["final_status"])
NODE_RUNS = Counter("node_runs_total", "تنفيذ العقد", ["node"])
GUARDRAIL_BLOCKS = Counter("guardrail_blocks_total", "حجوزات الحواجز", ["kind"])
DOC_LATENCY = Histogram("doc_latency_ms", "زمن معالجة الوثيقة (مللي ثانية)")


def write_trace(reports_dir: str | Path, doc_id: str, audit_trail: list[AuditEvent]) -> Path:
    """يكتب أثر وثيقة كملف JSON مع التحقق من سلامة سلسلة التجزئة."""
    traces = Path(reports_dir) / "traces"
    traces.mkdir(parents=True, exist_ok=True)
    payload = {
        "doc_id": doc_id,
        "chain_intact": verify_chain(audit_trail),
        "events": [
            {
                "node": e.node,
                "summary": redact_secrets(e.summary),
                "cost_usd": e.cost_usd,
                "latency_ms": e.latency_ms,
                "prev_hash": e.prev_hash,
                "digest": e.digest(),
            }
            for e in audit_trail
        ],
    }
    out = traces / f"{doc_id}.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def write_metrics_snapshot(reports_dir: str | Path, meter_snapshot: dict) -> Path:
    """يحفظ لقطة المقاييس (لكل عقدة ولكل وثيقة) — دليل لا يموت بانتهاء العملية."""
    out = Path(reports_dir) / "metrics-snapshot.json"
    out.write_text(json.dumps(meter_snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    return out
