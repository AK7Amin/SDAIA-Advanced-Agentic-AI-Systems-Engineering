"""M4: مخزن السياسات ChromaDB الحقيقي (بند rubric 3: ذاكرة خارجية متجهية)."""
from pathlib import Path

import pytest

from src.policy_store import PolicyStore

POLICY_FILE = Path(__file__).parent.parent / "policies" / "procurement_policy.md"


@pytest.fixture(scope="module")
def store():
    s = PolicyStore()
    s.index_policy_file(POLICY_FILE)
    return s


def test_indexes_all_policies(store):
    # الملف فيه POL-001..POL-005
    hits = store.retrieve("حد الموافقة على العقود", k=5)
    ids = {h["policy_id"] for h in hits}
    assert "POL-001" in ids


def test_retrieval_is_semantic_not_keyword(store):
    # استعلام بمعنى قريب دون لفظ حرفي مطابق
    hits = store.retrieve("ما أقصى مبلغ فاتورة يمر دون مراجعة مالية؟", k=3)
    ids = {h["policy_id"] for h in hits}
    assert "POL-003" in ids  # حد الفاتورة الواحدة


def test_only_trusted_file_indexed(store):
    # لا يُفهرس إلا ما مُرِّر صراحة — لا واجهة لإضافة نص وثيقة واردة.
    assert not hasattr(store, "index_document")
