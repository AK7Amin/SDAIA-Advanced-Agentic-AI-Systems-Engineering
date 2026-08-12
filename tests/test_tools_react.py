"""البند 1 من الرُبرِك الرسمي: أدوات حقيقية + نمط استدلال معلن (ReAct).

«وكيل يستدل ويستدعي أدوات/دوال حقيقية (لا مخرجات مبرمجة مسبقًا)… مع ذاكرة
قصيرة المدى (حالة محمولة عبر الخطوات)».
"""
import pytest

from src.agents.react import run_react
from src.tools import Tool, ToolError, ToolRegistry, calculator


@pytest.fixture
def registry():
    calls = {"policy": 0}

    def policy_lookup(q):
        calls["policy"] += 1
        return "POL-003: الحد الأقصى للفاتورة الواحدة 100000 ريال."

    reg = ToolRegistry([
        Tool("policy_lookup", "يبحث في السياسات", policy_lookup),
        Tool("calculator", "يحسب تعبيرًا", calculator),
    ])
    reg._calls = calls  # للفحص في الاختبار
    return reg


class TestCalculator:
    def test_arithmetic_and_comparison(self):
        assert calculator("320000 > 300000") == "True"
        assert calculator("45000 + 5000") == "50000"

    @pytest.mark.parametrize("evil", [
        "__import__('os').system('echo hi')",
        "open('x')",
        "1; import os",
        "[].__class__",
    ])
    def test_rejects_code_execution(self, evil):
        """حاسبة بمحلّل AST مقيَّد — لا تنفّذ كودًا (لا eval)."""
        with pytest.raises(ToolError):
            calculator(evil)


class TestRegistry:
    def test_unknown_tool_raises(self, registry):
        with pytest.raises(ToolError):
            registry.run("rm_rf", "/")

    def test_describe_lists_tools(self, registry):
        d = registry.describe()
        assert "policy_lookup" in d and "calculator" in d


class TestReActLoop:
    def test_agent_actually_calls_tools_then_answers(self, registry):
        """دورة كاملة: فعل ← ملاحظة ← فعل ← ملاحظة ← جواب نهائي."""
        replies = [
            "Thought: أحتاج السياسة\nAction: policy_lookup\nAction Input: حد الفاتورة",
            "Thought: أقارن المبلغ بالحد\nAction: calculator\nAction Input: 320000 > 100000",
            "Thought: تجاوز الحد\nFinal Answer: مخالف — يتجاوز POL-003",
        ]
        it = iter(replies)
        res = run_react(lambda _p: next(it), "دقّق الفاتورة", registry, max_steps=5)
        assert res.final_answer == "مخالف — يتجاوز POL-003"
        assert res.tool_calls == 2
        assert [s.action for s in res.steps if s.action] == ["policy_lookup", "calculator"]
        assert registry._calls["policy"] == 1        # الأداة نُفّذت فعلًا لا محاكاة
        assert res.steps[1].observation == "True"    # نتيجة حقيقية من الحاسبة

    def test_scratchpad_carries_short_term_memory(self, registry):
        """الملاحظات السابقة تُمرَّر في المطالبة التالية (ذاكرة قصيرة المدى)."""
        seen = []

        def llm(prompt):
            seen.append(prompt)
            if len(seen) == 1:
                return "Thought: ابحث\nAction: policy_lookup\nAction Input: حد"
            return "Thought: تم\nFinal Answer: مطابق"

        run_react(llm, "دقّق", registry, max_steps=3)
        assert "Observation:" in seen[1]
        assert "POL-003" in seen[1]     # ملاحظة الخطوة الأولى حاضرة في الثانية

    def test_loop_is_bounded(self, registry):
        """لا حلقة لانهائية: يتوقف عند الحد ويعلن الاستنفاد."""
        res = run_react(
            lambda _p: "Thought: مجددًا\nAction: policy_lookup\nAction Input: س",
            "مهمة", registry, max_steps=3,
        )
        assert res.exhausted is True
        assert res.final_answer is None
        assert res.tool_calls == 3

    def test_tool_error_is_fed_back_as_observation(self, registry):
        """خطأ الأداة يعود ملاحظةً للوكيل بدل إسقاط الحلقة."""
        replies = [
            "Thought: أجرب\nAction: calculator\nAction Input: __import__('os')",
            "Thought: أصحح\nFinal Answer: تم",
        ]
        it = iter(replies)
        res = run_react(lambda _p: next(it), "مهمة", registry, max_steps=3)
        assert "خطأ أداة" in res.steps[0].observation
        assert res.final_answer == "تم"


class TestForcedPolicyLookup:
    """لا حكم امتثال بلا مراجعة سياسة — يُفرض الاسترجاع إن قصّر النموذج."""

    def _agents(self, replies):
        from src.agents.real import RealAgents

        it = iter(replies)

        class _LLM:
            def invoke(self, prompt, **_):
                return next(it)

        class _Store:
            def retrieve(self, q, k=2):
                return [{"policy_id": "POL-003", "text": "حد الفاتورة 100000"}]

            def known_ids(self):
                return {"POL-001", "POL-003"}

        return RealAgents(_LLM(), _Store())

    def test_verdict_without_tool_use_is_rejected_and_retried(self):
        from src.schemas import ExtractedFields

        # الرد الأول: حكم فوري بلا أداة (سلوك مرفوض) ← يُفرض الاسترجاع ثم يُعاد السؤال.
        ag = self._agents([
            'Thought: واضح\nFinal Answer: {"verdict":"compliant","cited_policy_id":null,"reason":"-"}',
            'Thought: بعد السياسة\nFinal Answer: {"verdict":"violation","cited_policy_id":"POL-003","reason":"يتجاوز"}',
        ])
        verdict, res = ag.policy_check_with_tools(ExtractedFields(party="س", amount_sar=320000))
        assert res.tool_calls >= 1                      # نُفِّذت الأداة فعلًا
        assert res.steps[0].action == "policy_lookup"   # والاسترجاع أولًا
        assert verdict.cited_policy_id == "POL-003"     # والحكم استند لسياسة
