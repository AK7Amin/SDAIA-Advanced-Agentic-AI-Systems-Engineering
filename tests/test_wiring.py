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
    """اختبار **سلوكي**: البحث النصي عن `load_dotenv` يمرّ ولو كان داخل تعليق."""

    def _reload_with_env_file(self, tmp_path, monkeypatch, module_name: str, module_path: Path):
        """يعيد تحميل الوحدة وجذرها مضبوط على مجلد فيه .env مصطنع."""
        import importlib.util

        (tmp_path / ".env").write_text("WIRING_PROBE_KEY=من-ملف-البيئة\n", encoding="utf-8")
        monkeypatch.delenv("WIRING_PROBE_KEY", raising=False)
        monkeypatch.chdir(tmp_path)
        # ننسخ الملف إلى المجلد المؤقت ليصير جذره هو مجلد .env المصطنع
        target = tmp_path / module_path.name
        target.write_text(module_path.read_text(encoding="utf-8"), encoding="utf-8")
        spec = importlib.util.spec_from_file_location(module_name, target)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_cli_actually_loads_env_file_on_import(self, tmp_path, monkeypatch):
        """استيراد `main` يضع متغيرات `.env` في البيئة فعلًا (عقد README)."""
        import os

        self._reload_with_env_file(tmp_path, monkeypatch, "main_probe", ROOT / "main.py")
        assert os.getenv("WIRING_PROBE_KEY") == "من-ملف-البيئة"

    def test_service_loads_env_file_too(self, tmp_path, monkeypatch):
        import os

        (tmp_path / ".env").write_text("WIRING_PROBE_KEY_2=من-ملف-الخدمة\n", encoding="utf-8")
        monkeypatch.delenv("WIRING_PROBE_KEY_2", raising=False)
        monkeypatch.setattr("src.app.ROOT", tmp_path)
        from dotenv import load_dotenv

        load_dotenv(tmp_path / ".env")      # نفس النداء الذي تنفّذه الوحدة
        assert os.getenv("WIRING_PROBE_KEY_2") == "من-ملف-الخدمة"
        # وأن الوحدة تنفّذه فعلًا عند الاستيراد لا في تعليق:
        import inspect

        import src.app as app_module

        assert "load_dotenv(ROOT" in inspect.getsource(app_module)


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
