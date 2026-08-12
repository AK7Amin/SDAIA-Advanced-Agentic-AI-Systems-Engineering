"""الآثار الجانبية الحقيقية — أرشفة فعلية وإشعار مولَّد بقالب.

قبل هذه الوحدة كانت عقدتا `archive` و`notify` تغيّران حقل حالة فقط، فالنظام
«يقول أُرشفت» ولا يؤرشف. هنا تُنفَّذ الأفعال فعليًا:
- الأرشفة: نسخ الوثيقة إلى `archive/` + **قيد في قاعدة قرارات SQLite**
  (سجل قابل للاستعلام والتدقيق، لا مجرد ملف).
- الإشعار: توليد نص بقالب **Jinja2** وكتابته في `reports/notifications/`.

`NullEffects` يُحقن في الاختبارات فتبقى حتمية وبلا لمس قرص.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Template

from src.guardrails.path_guard import safe_doc_id

NOTIFICATION_TEMPLATE = Template(
    """إشعار معالجة وثيقة

المعرّف: {{ doc_id }}
الحالة النهائية: {{ final_status }}
النوع: {{ doc_type }}
{% if verdict %}حكم التدقيق: {{ verdict }}{% if policy %} (السياسة {{ policy }}){% endif %}
{% endif %}{% if amount %}القيمة: {{ amount }} ريال
{% endif %}
عدد خطوات المسار: {{ steps }}
وقت الإصدار: {{ issued_at }}

هذا إشعار آلي من وكيل دورة حياة الوثيقة.
""".strip()
)


class NullEffects:
    """بديل حتمي للاختبارات — يسجّل النداءات ولا يلمس القرص."""

    def __init__(self):
        self.archived: list[str] = []
        self.notified: list[str] = []

    def archive(self, doc_id: str, state: dict) -> str:
        self.archived.append(doc_id)
        return f"memory://archive/{doc_id}"

    def notify(self, doc_id: str, state: dict) -> str:
        self.notified.append(doc_id)
        return f"memory://notify/{doc_id}"


class FileEffects:
    """التنفيذ الحقيقي: قرص + قاعدة قرارات SQLite."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.archive_dir = self.root / "archive"
        self.notify_dir = self.root / "reports" / "notifications"
        self.db_path = self.root / "archive" / "decisions.sqlite"

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """CREATE TABLE IF NOT EXISTS decisions (
                doc_id TEXT PRIMARY KEY, final_status TEXT, doc_type TEXT,
                verdict TEXT, policy_id TEXT, amount_sar REAL,
                audit_head TEXT, decided_at TEXT
            )"""
        )
        return conn

    def archive(self, doc_id: str, state: dict) -> str:
        """يكتب الوثيقة المؤرشفة **ويقيّد القرار** في قاعدة قابلة للاستعلام."""
        safe = safe_doc_id(doc_id)
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        out = self.archive_dir / f"{safe}.txt"
        out.write_text(state.get("masked_text", ""), encoding="utf-8")

        verdict = state.get("policy_verdict")
        extraction = state.get("extraction")
        classification = state.get("classification")
        trail = state.get("audit_trail") or []
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO decisions VALUES (?,?,?,?,?,?,?,?)",
                (
                    safe,
                    state.get("final_status", ""),
                    classification.doc_type.value if classification else None,
                    verdict.verdict.value if verdict else None,
                    verdict.cited_policy_id if verdict else None,
                    extraction.amount_sar if extraction else None,
                    trail[-1].digest() if trail else "",
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
                ),
            )
        return str(out)

    def notify(self, doc_id: str, state: dict) -> str:
        """يولّد نص الإشعار بقالب Jinja2 ويكتبه ملفًا."""
        safe = safe_doc_id(doc_id)
        self.notify_dir.mkdir(parents=True, exist_ok=True)
        verdict = state.get("policy_verdict")
        extraction = state.get("extraction")
        classification = state.get("classification")
        plan = state.get("plan")
        text = NOTIFICATION_TEMPLATE.render(
            doc_id=safe,
            final_status=state.get("final_status", ""),
            doc_type=classification.doc_type.value if classification else "غير محدد",
            verdict=verdict.verdict.value if verdict else "",
            policy=verdict.cited_policy_id if verdict else "",
            amount=extraction.amount_sar if extraction else "",
            steps=len(plan.steps) if plan else 0,
            issued_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        out = self.notify_dir / f"{safe}.md"
        out.write_text(text, encoding="utf-8")
        return str(out)
