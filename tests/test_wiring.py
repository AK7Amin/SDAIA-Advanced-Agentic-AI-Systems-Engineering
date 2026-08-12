"""ادعاءات موصولة فعلًا بمسار التشغيل (قاعدة: الادعاء غير المنفَّذ خسارة صافية).

عيوب رُصدت حيًا وتحرسها هذه الاختبارات:
- README يَعِد بمفاتيح من `.env` ولم يكن أي مسار يحمّله → 401 من استنساخ نظيف.
- `dashboard.render` موجود ولم يكن ينادى من أي مكان → ملف قديم يدّعي مراقبة.
- عدّاد الأدوات كان يعرض جولة تدقيق واحدة بينما الأثر يحمل جولتين.
"""
import json
from pathlib import Path

import main as cli
from src.observability import dashboard

ROOT = Path(__file__).parent.parent


class TestEnvIsLoaded:
    def test_cli_loads_dotenv_on_import(self):
        """`main` يحمّل .env عند الاستيراد — عقد README منفَّذ لا موصوف."""
        src = (ROOT / "main.py").read_text(encoding="utf-8")
        assert "load_dotenv" in src

    def test_service_loads_dotenv_too(self):
        src = (ROOT / "src" / "app.py").read_text(encoding="utf-8")
        assert "load_dotenv" in src


class TestDashboardIsGenerated:
    def test_run_command_renders_the_dashboard(self, tmp_path, monkeypatch):
        """`main.py run` يولّد اللوحة من لقطة التشغيلة نفسها."""
        snap = tmp_path / "metrics-snapshot.json"
        cell = {"calls": 1, "tokens": 10, "latency_ms": 20, "ref_cost_usd": 0.1}
        snap.write_text(json.dumps({
            "total_tokens": 10, "total_latency_ms": 20, "total_ref_cost_usd": 0.1,
            "per_node": {"classify": cell},
            "per_doc": {"01_contract_compliant": cell},
        }), encoding="utf-8")
        out = dashboard.render(snap, tmp_path / "dashboard.html")
        assert out.exists() and "01_contract_compliant" in out.read_text(encoding="utf-8")
        # والوصل نفسه: أمر run ينادي render (لا ملف يتيم على القرص)
        assert "dashboard.render" in (ROOT / "main.py").read_text(encoding="utf-8")


class TestToolCounterMatchesTrace:
    def test_counter_accumulates_across_reflexion_rounds(self):
        """عدّاد الحالة = مجموع استدعاءات الجولتين، مطابقًا لأحداث الأثر."""
        from src.graph.build import build_graph
        from src.schemas import DocType, PolicyVerdict, ReviewAction, ReviewVerdict, Verdict
        from tests.conftest import _make_deps

        rounds = iter([Verdict.UNCERTAIN, Verdict.COMPLIANT])

        class _React:
            decision_source = "model"
            tool_calls = 2

            class _S:
                def __init__(self, a):
                    self.action, self.action_input, self.observation = a, "{}", "ok"

            steps = [_S("policy_lookup"), _S("calculator")]

        deps = _make_deps(DocType.CONTRACT, True, None, Verdict.COMPLIANT)
        deps.policy_check = lambda _f, _c="": (
            PolicyVerdict(verdict=next(rounds), reason="r"), _React()
        )
        deps.review = lambda _f, _v: ReviewVerdict(action=ReviewAction.REVISE, critique="أعد")
        state = build_graph(deps).invoke(
            {"masked_text": "عقد", "doc_id": "CNT-1", "extract_attempts": 0, "audit_trail": []},
            config={"configurable": {"thread_id": "tool_counter"}},
        )
        trace_tool_events = [e for e in state["audit_trail"] if e.node == "tool_call"]
        assert len(trace_tool_events) == 4          # جولتان × أداتان
        assert state["tool_calls"] == 4             # والعدّاد يطابقهما
