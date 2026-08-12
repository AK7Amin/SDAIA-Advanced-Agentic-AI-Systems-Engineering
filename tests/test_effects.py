"""الآثار الحقيقية: أرشفة فعلية + قيد قرار + إشعار مولَّد بقالب.

يغلق ملاحظة «archive/notify تغيّران الحالة فقط ولا تنفّذان شيئًا» — وهي أخطر
ملاحظة لو طُبّقت قاعدة «المحاكاة لا تُحتسب».
"""
import sqlite3

import pytest

from src.effects import FileEffects
from src.guardrails.path_guard import PathTraversalError
from src.schemas import Classification, DocType, ExtractedFields, PolicyVerdict, Verdict


@pytest.fixture
def state():
    return {
        "doc_id": "DOC-7",
        "masked_text": "عقد توريد بقيمة 30000 ريال",
        "final_status": "archived",
        "classification": Classification(doc_type=DocType.CONTRACT, confidence=0.9, rationale="-"),
        "extraction": ExtractedFields(party="شركة", amount_sar=30000, signed_date="2026-08-01"),
        "policy_verdict": PolicyVerdict(verdict=Verdict.COMPLIANT, reason="-"),
        "audit_trail": [],
    }


class TestArchive:
    def test_writes_real_file(self, tmp_path, state):
        fx = FileEffects(tmp_path)
        out = fx.archive("DOC-7", state)
        assert (tmp_path / "archive" / "DOC-7.txt").exists()
        assert "30000" in (tmp_path / "archive" / "DOC-7.txt").read_text(encoding="utf-8")
        # المسار المُعاد **نسبي** عمدًا: المطلق يسرّب اسم المستخدم وبنية جهازه
        # داخل آثار التدقيق الملتزَمة في ريبو عام.
        assert out == "archive/DOC-7.txt"

    def test_records_queryable_decision_row(self, tmp_path, state):
        """القرار يُقيَّد في قاعدة قابلة للاستعلام — لا مجرد ملف نصي."""
        fx = FileEffects(tmp_path)
        fx.archive("DOC-7", state)
        conn = sqlite3.connect(tmp_path / "archive" / "decisions.sqlite")
        row = conn.execute(
            "SELECT doc_id, final_status, doc_type, verdict, amount_sar FROM decisions"
        ).fetchone()
        conn.close()
        assert row[0] == "DOC-7"
        assert row[1] == "archived"
        assert row[2] == "contract"
        assert row[3] == "compliant"
        assert row[4] == 30000

    def test_rejects_traversal_doc_id(self, tmp_path, state):
        fx = FileEffects(tmp_path)
        with pytest.raises(PathTraversalError):
            fx.archive("../../evil", state)


class TestNotify:
    def test_renders_template_to_file(self, tmp_path, state):
        fx = FileEffects(tmp_path)
        out = fx.notify("DOC-7", state)
        text = (tmp_path / "reports" / "notifications" / "DOC-7.md").read_text(encoding="utf-8")
        assert "DOC-7" in text
        assert "archived" in text
        assert "30000" in text          # القالب يملأ القيم فعلًا
        assert "{{" not in text          # لا متغيرات قالب غير مُرندَرة
        assert out == "reports/notifications/DOC-7.md"     # نسبي لا مطلق
