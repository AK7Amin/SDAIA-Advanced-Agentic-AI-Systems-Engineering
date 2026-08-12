"""بناء الcheckpointer الدائم بمُسلسِل **مقيَّد بقائمة سماح** (بند rubric 5+4).

المشكلة الأمنية: مُسلسِل langgraph الافتراضي متساهل — يفك تسلسل أي نوع بايثون
مكتوب في قاعدة الcheckpoint (ويطبع تحذيرًا لكل نوع). ومن يكتب في قاعدة الحالة
يستطيع عندئذ دفع النظام لبناء كائنات لم نقصدها.

الحل: نعلن **قائمة سماح صريحة** بأنواعنا وحدها. ما ليس في القائمة يُرفض عند
فك التسلسل — نفس مبدأ «القائمة البيضاء» في بقية حواجز المشروع. وفائدة جانبية:
مخرجات التشغيل تنظف من تحذيرات الإصدار لأن السبب زال لا لأنه كُتم.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver

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

#: الأنواع الوحيدة المسموح ببنائها من قاعدة الحالة — عقودنا نحن لا غير.
ALLOWED_STATE_TYPES = (
    DocType,
    Verdict,
    ReviewAction,
    Classification,
    ExecutionPlan,
    ExtractedFields,
    PolicyVerdict,
    ReviewVerdict,
    AuditEvent,
)


def strict_serializer() -> JsonPlusSerializer:
    """مُسلسِل يقبل أنواع المشروع فقط (بدل «كل شيء» الافتراضي)."""
    return JsonPlusSerializer(allowed_msgpack_modules=list(ALLOWED_STATE_TYPES))


def make_sqlite_saver(db_path: str | Path) -> SqliteSaver:
    """`SqliteSaver` دائم على القرص.

    مزلق مثبت بالتجربة: `SqliteSaver` **ليس** مدير سياق — يُبنى باتصال جاهز،
    و`from_conn_string` وحده هو الـcontext manager.
    """
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    return SqliteSaver(conn, serde=strict_serializer())
