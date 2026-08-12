"""البند 1: واجهة الأدوات بنمط MCP — إعلان، استدعاء منظَّم، تحقق، سجل تنفيذ.

الرُبرِك يطلب «function calling أو واجهة أدوات بنمط MCP». ReAct نمط استدلال،
وهو شرط **منفصل** عن واجهة الأدوات — هذا الملف يغطي الشرط الثاني وحده.
"""
import pytest

from src.agents.react import run_react
from src.tools import Tool, ToolCall, ToolError, ToolRegistry, calculator


@pytest.fixture
def registry():
    def policy_lookup(query):
        return f"POL-003 :: {query[:20]}"

    return ToolRegistry([
        Tool("policy_lookup", "يبحث في السياسات", policy_lookup,
             {"type": "object",
              "properties": {"query": {"type": "string"}},
              "required": ["query"]}),
        Tool("calculator", "يحسب تعبيرًا", calculator,
             {"type": "object",
              "properties": {"expression": {"type": "string"}},
              "required": ["expression"]}),
    ])


class TestDeclaration:
    def test_list_tools_returns_mcp_shaped_descriptors(self, registry):
        """`list_tools` يعيد نفس حقول `tools/list` في MCP: name/description/inputSchema."""
        tools = {t["name"]: t for t in registry.list_tools()}
        assert set(tools) == {"policy_lookup", "calculator"}
        schema = tools["policy_lookup"]["inputSchema"]
        assert schema["type"] == "object"
        assert schema["required"] == ["query"]
        assert tools["policy_lookup"]["description"]

    def test_schema_is_inferred_when_not_declared(self):
        """أداة بلا مخطط صريح تستنتجه من توقيعها — لا أداة بلا عقد."""
        reg = ToolRegistry([Tool("echo", "يعيد النص", lambda text: text)])
        assert reg.list_tools()[0]["inputSchema"]["required"] == ["text"]


class TestValidatedDispatch:
    def test_structured_call_executes_and_returns_result(self, registry):
        res = registry.dispatch(ToolCall("calculator", {"expression": "2 + 2"}))
        assert res.ok and res.output == "4"

    def test_missing_argument_is_rejected_before_execution(self, registry):
        """التحقق يسبق تنفيذ كود الأداة — لا استدعاء بوسائط ناقصة."""
        with pytest.raises(ToolError, match="ناقصة"):
            registry.dispatch(ToolCall("policy_lookup", {}))

    def test_unknown_argument_is_rejected(self, registry):
        """وسيط زائد يُرفض حتى لو اكتملت الوسائط المطلوبة — لا تمرير صامت."""
        with pytest.raises(ToolError, match="غير معروفة"):
            registry.dispatch(ToolCall("calculator", {"expression": "1+1", "shell": "rm"}))

    def test_wrong_type_is_rejected(self):
        reg = ToolRegistry([
            Tool("cap", "يحدّ", lambda limit: str(limit),
                 {"type": "object", "properties": {"limit": {"type": "number"}},
                  "required": ["limit"]}),
        ])
        with pytest.raises(ToolError, match="نوع خاطئ"):
            reg.dispatch(ToolCall("cap", {"limit": "كثير"}))

    def test_unknown_tool_is_rejected(self, registry):
        with pytest.raises(ToolError):
            registry.dispatch(ToolCall("rm_rf", {"path": "/"}))


class TestParsing:
    def test_json_arguments_are_parsed_into_named_args(self, registry):
        call = registry.parse_call("policy_lookup", '{"query": "حد الفاتورة"}')
        assert call.arguments == {"query": "حد الفاتورة"}

    def test_bare_value_maps_to_the_single_required_argument(self, registry):
        """تسامح مع النماذج الصغيرة: قيمة مفردة تُسنَد للوسيط الوحيد."""
        call = registry.parse_call("calculator", "5 > 1")
        assert call.arguments == {"expression": "5 > 1"}


class TestExecutionLog:
    def test_every_call_is_recorded_with_arguments_and_outcome(self, registry):
        registry.dispatch(ToolCall("calculator", {"expression": "3 * 3"}))
        with pytest.raises(ToolError):
            registry.dispatch(ToolCall("calculator", {"expression": "open('x')"}))
        log = registry.execution_log
        assert [r.name for r in log] == ["calculator", "calculator"]
        assert log[0].ok is True and log[0].output == "9"
        assert log[1].ok is False          # الفشل يُقيَّد أيضًا، لا يُخفى
        assert log[0].arguments == {"expression": "3 * 3"}

    def test_react_loop_dispatches_through_the_same_registry(self, registry):
        """ReAct لا يملك مسارًا جانبيًا — كل أفعاله تمر بالموزِّع نفسه."""
        replies = [
            'Thought: أبحث\nAction: policy_lookup\nAction Input: {"query": "حد"}',
            "Thought: تم\nFinal Answer: مطابق",
        ]
        it = iter(replies)
        res = run_react(lambda _p: next(it), "دقّق", registry, max_steps=3)
        assert res.final_answer == "مطابق"
        assert len(registry.execution_log) == 1
        assert registry.execution_log[0].arguments == {"query": "حد"}
        assert res.steps[0].call == ToolCall("policy_lookup", {"query": "حد"})


class TestDecisionSourceHonesty:
    """لا يُنسب للنموذج اختيارُ أداةٍ فرضها النظام."""

    def _agents(self, replies):
        from src.agents.real import RealAgents

        it = iter(replies)

        class _LLM:
            def invoke(self, prompt, **_):
                return next(it)

        class _Store:
            def retrieve(self, q, k=2):
                return [{"policy_id": "POL-003", "text": "حد الفاتورة 100000"}]

        return RealAgents(_LLM(), _Store())

    def test_model_chosen_tool_is_labelled_model(self):
        from src.schemas import ExtractedFields

        ag = self._agents([
            'Thought: أبحث\nAction: policy_lookup\nAction Input: {"query": "حد"}',
            'Thought: تم\nFinal Answer: {"verdict":"compliant","cited_policy_id":"POL-003","reason":"-"}',
        ])
        _v, res = ag.policy_check_with_tools(ExtractedFields(party="س", amount_sar=1))
        assert res.decision_source == "model"

    def test_enforced_lookup_is_labelled_policy_enforced(self):
        from src.schemas import ExtractedFields

        ag = self._agents([
            'Thought: واضح\nFinal Answer: {"verdict":"compliant","cited_policy_id":null,"reason":"-"}',
            'Thought: بعد السياسة\nFinal Answer: {"verdict":"violation","cited_policy_id":"POL-003","reason":"يتجاوز"}',
        ])
        _v, res = ag.policy_check_with_tools(ExtractedFields(party="س", amount_sar=320000))
        assert res.decision_source == "policy_enforced"   # لا ندّعي أن النموذج اختارها

    def test_audit_trail_marks_the_enforced_call_distinctly(self):
        """أثر التدقيق نفسه يفرّق بين أداة اختارها النموذج وأخرى فُرضت."""
        from src.graph.build import build_graph
        from src.schemas import DocType, ExtractedFields, PolicyVerdict, Verdict
        from tests.conftest import _make_deps

        class _React:
            decision_source = "policy_enforced"
            tool_calls = 2

            class _S:
                def __init__(self, a, i, o):
                    self.action, self.action_input, self.observation = a, i, o

            steps = [_S("policy_lookup", '{"query":"x"}', "POL-003"),
                     _S("calculator", '{"expression":"1>0"}', "True")]

        deps = _make_deps(DocType.CONTRACT, True, None, Verdict.COMPLIANT)
        deps.policy_check = lambda _f, _c="": (
            PolicyVerdict(verdict=Verdict.COMPLIANT, reason="stub"), _React()
        )
        state = build_graph(deps).invoke(
            {"masked_text": "عقد", "doc_id": "SRC-1", "extract_attempts": 0, "audit_trail": []},
            config={"configurable": {"thread_id": "decision_source"}},
        )
        tool_events = [e.summary for e in state["audit_trail"] if e.node == "tool_call"]
        assert "[مصدر=policy_enforced]" in tool_events[0]
        assert "[مصدر=model]" in tool_events[1]
        assert state["decision_source"] == "policy_enforced"
        policy_event = next(e for e in state["audit_trail"] if e.node == "policy_check")
        assert "مصدر_القرار=policy_enforced" in policy_event.summary
