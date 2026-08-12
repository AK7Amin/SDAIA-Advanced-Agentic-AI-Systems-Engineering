"""عيوب كشفتها المراجعة الثانية — كل اختبار هنا يحرس إصلاحًا بعينه."""
import threading

from src.llm import LLMLayer


class TestPerRequestState:
    """حالة النداء لكل طلب لا لكل كائن — الخدمة تشارك LLMLayer واحدًا."""

    def test_two_threads_do_not_share_doc_attribution(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "k")
        layer = LLMLayer()
        seen = {}
        barrier = threading.Barrier(2)

        def worker(doc_id):
            layer.active_doc_id = doc_id
            barrier.wait()                 # يضمن التداخل الفعلي لا التتابع
            seen[doc_id] = layer.active_doc_id

        threads = [threading.Thread(target=worker, args=(d,)) for d in ("DOC-A", "DOC-B")]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert seen == {"DOC-A": "DOC-A", "DOC-B": "DOC-B"}   # لا تبادل نسبة تكلفة

    def test_budget_guard_is_not_shared_between_threads(self, monkeypatch):
        from src.guardrails.budget import BudgetGuard

        monkeypatch.setenv("LLM_API_KEY", "k")
        layer = LLMLayer()
        results = {}

        def worker(name, limit):
            layer.budget = BudgetGuard(max_calls=limit)
            layer.budget.charge()
            results[name] = layer.budget.calls

        threads = [threading.Thread(target=worker, args=a) for a in (("a", 1), ("b", 5))]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert results == {"a": 1, "b": 1}      # عدّاد مستقل لكل خيط


class TestReActOrdering:
    """ردٌّ يحمل فعلًا وجوابًا نهائيًا: يفوز الأسبق نصًا."""

    def _registry(self):
        from src.tools import Tool, ToolRegistry

        return ToolRegistry([Tool("policy_lookup", "يبحث", lambda query: f"POL-003 :: {query}")])

    def test_action_before_final_answer_is_executed(self):
        from src.agents.react import run_react

        replies = [
            # الفعل **قبل** الجواب في نفس الرد: يجب أن يُنفَّذ الفعل لا أن يُبتلع
            'Thought: أبحث\nAction: policy_lookup\nAction Input: {"query": "حد"}\n'
            "Final Answer: مطابق",
            "Thought: تم\nFinal Answer: مطابق فعلًا",
        ]
        it = iter(replies)
        res = run_react(lambda _p: next(it), "دقّق", self._registry(), max_steps=3)
        assert res.tool_calls == 1                    # لم تُبتلع الأداة صامتًا
        assert res.final_answer == "مطابق فعلًا"

    def test_final_answer_before_action_ends_the_loop(self):
        from src.agents.react import run_react

        res = run_react(
            # الجواب **قبل** الفعل: الحلقة تنتهي ولا يُنفَّذ فعل متأخر
            lambda _p: 'Thought: حسمت\nFinal Answer: مطابق\nAction: policy_lookup\n'
                       'Action Input: {"query": "متأخر"}',
            "دقّق", self._registry(), max_steps=3,
        )
        assert res.final_answer == "مطابق" and res.tool_calls == 0


class TestDecisiveVerdictNeedsPolicy:
    """لا حكم حاسم بلا سند — الثقة بلا استشهاد أسوأ من عدم الحسم."""

    def _agents(self):
        from src.agents.real import RealAgents

        class _LLM:
            def invoke(self, prompt, **_):
                return "{}"

        class _Store:
            def retrieve(self, q, k=2):
                return [{"policy_id": "POL-003", "text": "حد"}]

            def known_ids(self):
                return {"POL-001", "POL-003"}

        return RealAgents(_LLM(), _Store())

    def test_compliant_without_citation_is_downgraded(self):
        from src.schemas import PolicyVerdict, Verdict

        out = self._agents().validate_citation(
            PolicyVerdict(verdict=Verdict.COMPLIANT, cited_policy_id=None, reason="يبدو سليمًا")
        )
        assert out.verdict == Verdict.UNCERTAIN
        assert "بلا استشهاد" in out.reason

    def test_uncertain_without_citation_passes(self):
        from src.schemas import PolicyVerdict, Verdict

        v = PolicyVerdict(verdict=Verdict.UNCERTAIN, cited_policy_id=None, reason="غامض")
        assert self._agents().validate_citation(v).verdict == Verdict.UNCERTAIN


class TestArabicDigitPII:
    """PII بالأرقام العربية-الهندية كان يمر بلا تقنيع — في مشروع عربي بالكامل."""

    def test_saudi_id_in_arabic_digits_is_masked(self):
        from src.guardrails.output_guard import mask_pii

        out = mask_pii("رقم الهوية: ١٠٢٣٤٥٦٧٨٩ للطرف الثاني")
        assert "١٠٢٣٤٥٦٧٨٩" not in out and "**ID-REDACTED**" in out

    def test_mobile_in_arabic_digits_is_masked(self):
        from src.guardrails.output_guard import mask_pii

        out = mask_pii("الجوال ٠٥٠١٢٣٤٥٦٧ للتواصل")
        assert "٠٥٠١٢٣٤٥٦٧" not in out and "**PHONE-REDACTED**" in out

    def test_latin_digits_still_masked(self):
        from src.guardrails.output_guard import mask_pii

        out = mask_pii("الهوية 1023456789 والجوال 0501234567 والآيبان SA0380000000608010167519")
        assert "1023456789" not in out and "0501234567" not in out
        assert "SA0380000000608010167519" not in out

    def test_amounts_are_not_masked_in_either_script(self):
        """المبالغ ليست PII — الإفراط في التقنيع يفسد الحقول المستخرجة."""
        from src.guardrails.output_guard import mask_pii

        assert mask_pii("قيمة العقد: 30000 ريال") == "قيمة العقد: 30000 ريال"
        assert mask_pii("قيمة العقد: ٣٠٠٠٠ ريال") == "قيمة العقد: ٣٠٠٠٠ ريال"

    def test_untouched_text_is_returned_verbatim(self):
        """لا تشويه لنص الوثيقة: الأرقام العربية تبقى عربية حيث لا تقنيع."""
        from src.guardrails.output_guard import mask_pii

        doc = "عقد بتاريخ ٢٠٢٦-٠٣-٠١ ومدة ١٢ شهرًا"
        assert mask_pii(doc) == doc

    def test_mixed_scripts_in_one_document(self):
        from src.guardrails.output_guard import mask_pii

        out = mask_pii("هوية ١٠٢٣٤٥٦٧٨٩ وأخرى 2098765432 ومبلغ ٥٠٠٠٠")
        assert out.count("**ID-REDACTED**") == 2
        assert "٥٠٠٠٠" in out          # المبلغ سليم بين تقنيعين
