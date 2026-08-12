"""خدمة FastAPI — الأثر السحابي في البند 5 لم يكن يمسّه اختبار واحد.

لا نداء نموذج هنا: المخطط يُستبدل بمخطط stub عبر `_STATE`، فنختبر عقد الخدمة
نفسه (المسارات، والعزل بين الطلبات، وبوابة الاعتماد) لا ذكاء النموذج.
"""
import pytest
from fastapi.testclient import TestClient

from src import app as app_module
from src.schemas import DocType, Verdict


@pytest.fixture
def client(monkeypatch, tmp_path, graph_with_stubs):
    """عميل اختبار بمخطط حتمي وتقارير في مجلد مؤقت."""
    graph = graph_with_stubs(
        classification=DocType.CONTRACT, extraction_complete=True, verdict=Verdict.COMPLIANT
    )

    class _LLM:
        active_doc_id = "-"
        budget = None

    monkeypatch.setitem(app_module._STATE, "graph", graph)
    monkeypatch.setitem(app_module._STATE, "llm", _LLM())
    monkeypatch.setattr(app_module, "ROOT", tmp_path)
    return TestClient(app_module.app)


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_metrics_endpoint_serves_prometheus_text(client):
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "docs_processed_total" in r.text


def test_process_returns_status_and_thread(client):
    r = client.post("/process", json={"doc_id": "svc1", "text": "عقد توريد بقيمة 30000 ريال"})
    assert r.status_code == 200
    body = r.json()
    assert body["final_status"] == "archived"
    assert body["thread_id"].startswith("api-")     # خيط خاص بالطلب لا doc_id


def test_two_requests_same_doc_id_do_not_merge_into_one_trace(client, tmp_path):
    """العيب الذي بُني `verify-traces` لكشفه: طلبان بنفس المعرّف يستأنفان الخيط.

    النتيجة كانت أثرًا واحدًا فيه عقدة `ingest` مرتين — تشغيلتان في ملف واحد.
    """
    import json

    payload = {"doc_id": "svc_same", "text": "عقد توريد بقيمة 30000 ريال"}
    first = client.post("/process", json=payload).json()
    second = client.post("/process", json=payload).json()
    assert first["thread_id"] != second["thread_id"]

    trace = json.loads(
        (tmp_path / "reports" / "generated" / "traces" / "svc_same.json").read_text(encoding="utf-8")
    )
    nodes = [e["node"] for e in trace["events"]]
    assert nodes.count("ingest") == 1               # لا تشغيلتان في أثر واحد
    assert trace["chain_intact"] is True


def test_client_cannot_disable_guardrails(client):
    """حقل `guardrails` ليس في عقد الإدخال — تمريره لا يعطّل شيئًا."""
    r = client.post(
        "/process", json={"doc_id": "svc2", "text": "عقد 30000 ريال", "guardrails": False}
    )
    assert r.status_code == 200
    assert "guardrails" not in app_module.DocIn.model_fields


class TestApprovalGate:
    """بوابة الموافقة تعتمد عقدًا مخالفًا بنداء واحد — فلا تُفتح بلا اعتماد."""

    def test_disabled_when_no_token_configured(self, client, monkeypatch):
        monkeypatch.delenv("APPROVAL_API_TOKEN", raising=False)
        r = client.post("/resume", json={"thread_id": "t1", "decision": "approve"})
        assert r.status_code == 503        # المنع هو الافتراض الآمن، لا السماح

    def test_rejects_wrong_token(self, client, monkeypatch):
        monkeypatch.setenv("APPROVAL_API_TOKEN", "correct-token")
        r = client.post(
            "/resume",
            json={"thread_id": "t1", "decision": "approve"},
            headers={"X-Approval-Token": "wrong"},
        )
        assert r.status_code == 401

    def test_full_hitl_cycle_through_the_service(
        self, monkeypatch, tmp_path, graph_with_stubs
    ):
        """الدورة كاملة عبر الخدمة: مخالفة تتوقف ← اعتماد صحيح ← تُؤرشف."""

        class _LLM:
            active_doc_id = "-"
            budget = None

        graph = graph_with_stubs(
            classification=DocType.INVOICE, extraction_complete=True, verdict=Verdict.VIOLATION
        )
        monkeypatch.setitem(app_module._STATE, "graph", graph)
        monkeypatch.setitem(app_module._STATE, "llm", _LLM())
        monkeypatch.setattr(app_module, "ROOT", tmp_path)
        monkeypatch.setenv("APPROVAL_API_TOKEN", "correct-token")
        c = TestClient(app_module.app)

        started = c.post("/process", json={"doc_id": "svc_hitl", "text": "فاتورة 320000 ريال"})
        assert started.json()["final_status"] == "awaiting_approval"   # توقف فعلًا

        resumed = c.post(
            "/resume",
            json={"thread_id": started.json()["thread_id"], "decision": "approve"},
            headers={"X-Approval-Token": "correct-token"},
        )
        assert resumed.status_code == 200
        assert resumed.json()["final_status"] == "archived"            # واستأنف فعلًا
