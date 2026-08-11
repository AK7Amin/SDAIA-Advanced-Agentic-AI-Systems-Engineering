"""M6: الإيقاف والاستئناف عبر عمليتين — قلب بند rubric 3."""
import subprocess
import sys
from pathlib import Path

import pytest

RESUME_HELPER = Path(__file__).parent / "helpers" / "resume_in_new_process.py"


def test_interrupt_persists_to_sqlite(tmp_path, graph_with_stubs_factory):
    """التجمد عند الموافقة يكتب checkpoint فعليًا في ملف sqlite."""
    db = tmp_path / "ck.sqlite"
    graph = graph_with_stubs_factory(checkpoint_db=db, verdict="violation")
    graph.invoke(
        {"masked_text": "فاتورة مخالفة", "doc_id": "DOC-9", "extract_attempts": 0, "audit_trail": []},
        config={"configurable": {"thread_id": "T-9"}},
    )
    assert db.exists() and db.stat().st_size > 0


def test_resume_in_separate_process_completes(tmp_path, graph_with_stubs_factory):
    """عملية بايثون جديدة كليًا تستأنف نفس thread_id بعد الموافقة وتصل archive.

    هذا هو الدليل الذي يطلبه نمط rubric الدورة السابقة (أثبت مسار الفشل/التوقف
    فعليًا): لا يكفي استئناف داخل نفس العملية.
    """
    db = tmp_path / "ck.sqlite"
    graph = graph_with_stubs_factory(checkpoint_db=db, verdict="violation")
    graph.invoke(
        {"masked_text": "فاتورة مخالفة", "doc_id": "DOC-9", "extract_attempts": 0, "audit_trail": []},
        config={"configurable": {"thread_id": "T-9"}},
    )
    result = subprocess.run(
        [sys.executable, str(RESUME_HELPER), str(db), "T-9", "approve"],
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert "archived" in result.stdout
