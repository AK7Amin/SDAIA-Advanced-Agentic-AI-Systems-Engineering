"""حلقة ReAct — نمط استدلال + فعل (البند 1).

دورة: فكرة Thought ← فعل Action (استدعاء أداة) ← ملاحظة Observation ← فكرة...
حتى جواب نهائي Final Answer أو بلوغ حد الخطوات. مستقلة عن النموذج: تقرأ
الفعل من نص النموذج (لا تعتمد على دعم function-calling الأصلي).

الذاكرة قصيرة المدى (البند 1): «دفتر» scratchpad يحمل كل الأفكار والأفعال
والملاحظات عبر الخطوات، ويُمرَّر كاملًا في كل استدعاء.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from src.tools import ToolCall, ToolError, ToolRegistry

_ACTION_RE = re.compile(r"Action:\s*([A-Za-z_]+)\s*\n\s*Action Input:\s*(.+?)(?:\n|$)", re.DOTALL)
_FINAL_RE = re.compile(r"Final Answer:\s*(.+)", re.DOTALL)

REACT_INSTRUCTIONS = """أنت وكيل يحل المهمة عبر دورة تفكير وأدوات.
الأدوات المتاحة (بين القوسين اسم كل وسيط ونوعه):
{tools}

استعمل هذا النسق حرفيًا، خطوة واحدة كل رد:
Thought: <تفكيرك>
Action: <اسم الأداة>
Action Input: <كائن JSON بالوسائط المسماة، مثل {{"query": "حد الفاتورة"}}>

وحين تجهز بالجواب:
Thought: <خلاصتك>
Final Answer: <الجواب النهائي>

المهمة: {task}

{scratchpad}"""


@dataclass
class ReActStep:
    thought: str
    action: str | None
    action_input: str | None
    observation: str | None
    #: الاستدعاء المنظَّم بعد التحقق من المخطط (None إن لم يُستدعَ أداة).
    call: ToolCall | None = None


@dataclass
class ReActResult:
    final_answer: str | None
    steps: list[ReActStep] = field(default_factory=list)
    exhausted: bool = False   # بلغ حد الخطوات دون جواب نهائي
    #: مسار وصول الحكم: "model" | "policy_enforced" | "fallback_direct_retrieval".
    decision_source: str = "model"
    #: هل **فرض النظام** الاستدعاء الأول؟ علم مستقل عن `decision_source` عمدًا:
    #: مسار السقوط يكتب فوق الأخير، وكان ذلك يُلبس الأداة المفروضة وسم "model"
    #: في أثر التدقيق — أي أن ميزة الصدق نفسها كانت تكذب في هذا الفرع.
    forced_first_call: bool = False

    @property
    def tool_calls(self) -> int:
        return sum(1 for s in self.steps if s.action)


def _parse_thought(text: str) -> str:
    m = re.search(r"Thought:\s*(.+?)(?:\nAction:|\nFinal Answer:|$)", text, re.DOTALL)
    return m.group(1).strip() if m else ""


def run_react(llm_call, task: str, registry: ToolRegistry, max_steps: int = 4) -> ReActResult:
    """يشغّل حلقة ReAct. `llm_call(prompt) -> str` هو مقبس النموذج (يسهل ترقيعه).

    الحلقة محدودة بـ`max_steps` (لا لانهاية — نفس مبدأ حلقات المخطط).
    """
    scratchpad = ""
    result = ReActResult(final_answer=None)
    for step_i in range(max_steps):
        # في الخطوة الأخيرة يُطلب الحسم صراحةً — وإلا استنفد النموذج الحلقة
        # بأدوات متكررة بلا جواب (سلوك رُصد حيًا) فيضيع استدلاله كله.
        closing = (
            "\n\n**هذه آخر خطوة مسموحة**: لا تستدعِ أداة أخرى، أعطِ Final Answer الآن "
            "بناءً على الملاحظات أعلاه."
            if step_i == max_steps - 1
            else ""
        )
        prompt = REACT_INSTRUCTIONS.format(
            tools=registry.describe(), task=task, scratchpad=scratchpad
        ) + closing
        text = llm_call(prompt) or ""

        final = _FINAL_RE.search(text)
        action_match = _ACTION_RE.search(text)
        # ردٌّ يحمل الاثنين: يفوز **الأسبق نصًا**. تفضيل الجواب دائمًا كان يُسقط
        # استدعاء أداة قرره النموذج صامتًا — فيضيع دليل البند 1 ويُحكم بلا أداة.
        if final and action_match and action_match.start() < final.start():
            final = None
        if final:
            # `_FINAL_RE` جشع (DOTALL): يبتلع كل ما بعده. فإن أتبع النموذج جوابَه
            # بفعل متأخر، قُصَّ الجواب عنده — وإلا حُشِر نص الفعل داخل الجواب.
            answer = final.group(1).strip()
            trailing = re.search(r"\n\s*Action:\s", answer)
            if trailing:
                answer = answer[: trailing.start()].strip()
            result.final_answer = answer
            result.steps.append(ReActStep(_parse_thought(text), None, None, None))
            return result

        m = action_match
        if not m:
            # النموذج لم يلتزم النسق — أوقف الحلقة (يتكفّل النادِي بمسار احتياطي).
            result.steps.append(ReActStep(_parse_thought(text), None, None, None))
            result.exhausted = True
            return result

        action, action_input = m.group(1).strip(), m.group(2).strip()
        # نص النموذج ← استدعاء منظَّم ← موزِّع واحد يتحقق من المخطط قبل التنفيذ.
        call: ToolCall | None = None
        try:
            call = registry.parse_call(action, action_input)
            observation = registry.dispatch(call).output
            # الوسائط وحدها — اسم الأداة يُطبع بجوارها فلا يتكرر في الأثر.
            rendered = json.dumps(call.arguments, ensure_ascii=False)
        except ToolError as e:
            observation = f"خطأ أداة: {e}"
            rendered = action_input
        result.steps.append(ReActStep(_parse_thought(text), action, rendered, observation, call))
        scratchpad += (
            f"Thought: {_parse_thought(text)}\nAction: {action}\n"
            f"Action Input: {rendered}\nObservation: {observation}\n"
        )
    result.exhausted = True
    return result
