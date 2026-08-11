"""M5: مسارات المخطط الخمسة — الحواف الشرطية والحلقة (بند rubric 1).

المخطط يعمل على masked_text فقط (raw_text لا يدخل الحالة — نقد B3).
كل اختبار يستخدم thread_id فريدًا لئلا تتسرب الحالة بين الاختبارات.
"""
import pytest

from src.schemas import DocType, Verdict


def _run(graph, doc_text, thread):
    return graph.invoke(
        {"masked_text": doc_text, "doc_id": "DOC-1", "extract_attempts": 0, "audit_trail": []},
        config={"configurable": {"thread_id": thread}},
    )


def test_compliant_path_archives(monkeypatch, compliant_contract_ar, graph_with_stubs):
    """مطابق: classify→extract→policy_check→archive→notify."""
    graph = graph_with_stubs(
        classification=DocType.CONTRACT,
        extraction_complete=True,
        verdict=Verdict.COMPLIANT,
    )
    state = _run(graph, compliant_contract_ar, "compliant")
    assert state["final_status"] == "archived"
    nodes_visited = [e.node for e in state["audit_trail"]]
    assert nodes_visited[-1] == "notify"


def test_unknown_type_quarantined(graph_with_stubs):
    graph = graph_with_stubs(classification=DocType.UNKNOWN)
    state = _run(graph, "نص عشوائي لا يشبه أي وثيقة", "unknown")
    assert state["final_status"] == "quarantined"
    assert any(e.node == "quarantine" for e in state["audit_trail"])


def test_violation_pauses_for_human(graph_with_stubs, over_limit_invoice_ar):
    """مخالفة: يتجمد عند escalate بانتظار الموافقة — لا يصل archive."""
    graph = graph_with_stubs(
        classification=DocType.INVOICE, extraction_complete=True, verdict=Verdict.VIOLATION
    )
    state = _run(graph, over_limit_invoice_ar, "violation")
    assert state["final_status"] == "awaiting_approval"
    assert not any(e.node == "archive" for e in state["audit_trail"])


def test_incomplete_extraction_loops_then_succeeds(graph_with_stubs):
    """الحلقة: استخراج ناقص ← إعادة بتلميح ← نجاح — بند الحلقة في rubric 1."""
    graph = graph_with_stubs(
        classification=DocType.CONTRACT,
        extraction_attempts=["missing", "complete"],
        verdict=Verdict.COMPLIANT,
    )
    state = _run(graph, "عقد ناقص البيانات ثم يكتمل", "loop_ok")
    extract_visits = [e for e in state["audit_trail"] if e.node == "extract"]
    assert len(extract_visits) == 2
    assert state["final_status"] == "archived"


def test_extraction_loop_bounded_then_escalates(graph_with_stubs):
    """الحلقة محدودة: محاولتان ثم تصعيد — لا حلقة لانهائية."""
    graph = graph_with_stubs(
        classification=DocType.CONTRACT,
        extraction_attempts=["missing", "missing", "missing"],
    )
    state = _run(graph, "عقد لا يكتمل استخراجه أبدًا", "loop_max")
    extract_visits = [e for e in state["audit_trail"] if e.node == "extract"]
    assert len(extract_visits) == 2
    assert state["final_status"] == "awaiting_approval"


def test_letter_skips_extraction_via_plan_route(graph_with_stubs):
    """plan_route يغيّر تدفق التحكم فعلًا: الخطاب يتخطى الاستخراج إلى التدقيق.

    هذا ما يمنع تصنيف النظام «سلسلة خطية مقنّعة» في بند rubric 1.
    """
    graph = graph_with_stubs(classification=DocType.LETTER, verdict=Verdict.COMPLIANT)
    state = _run(graph, "خطاب رسمي بلا التزام مالي", "letter_path")
    nodes = [e.node for e in state["audit_trail"]]
    assert "plan_route" in nodes
    assert "extract" not in nodes          # تُخطّي فعليًا
    assert "policy_check" in nodes
    assert state["final_status"] == "archived"


def test_audit_trail_appends_never_replaces(graph_with_stubs, compliant_contract_ar):
    """reducer الحالة يجمع أحداث التدقيق ولا يستبدلها."""
    graph = graph_with_stubs(
        classification=DocType.CONTRACT, extraction_complete=True, verdict=Verdict.COMPLIANT
    )
    state = _run(graph, compliant_contract_ar, "audit")
    assert len(state["audit_trail"]) >= 5
