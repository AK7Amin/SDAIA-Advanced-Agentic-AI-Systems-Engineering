"""حلقة ReAct — نمط استدلال + فعل (البند 1).

دورة: فكرة Thought ← فعل Action (استدعاء أداة) ← ملاحظة Observation ← فكرة...
حتى جواب نهائي Final Answer أو بلوغ حد الخطوات. مستقلة عن النموذج: تقرأ
الفعل من نص النموذج (لا تعتمد على دعم function-calling الأصلي).

الذاكرة قصيرة المدى (البند 1): «دفتر» scratchpad يحمل كل الأفكار والأفعال
والملاحظات عبر الخطوات، ويُمرَّر كاملًا في كل استدعاء.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.tools import ToolError, ToolRegistry

_ACTION_RE = re.compile(r"Action:\s*([A-Za-z_]+)\s*\n\s*Action Input:\s*(.+?)(?:\n|$)", re.DOTALL)
_FINAL_RE = re.compile(r"Final Answer:\s*(.+)", re.DOTALL)

REACT_INSTRUCTIONS = """أنت وكيل يحل المهمة عبر دورة تفكير وأدوات.
الأدوات المتاحة:
{tools}

استعمل هذا النسق حرفيًا، خطوة واحدة كل رد:
Thought: <تفكيرك>
Action: <اسم الأداة>
Action Input: <المدخل>

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


@dataclass
class ReActResult:
    final_answer: str | None
    steps: list[ReActStep] = field(default_factory=list)
    exhausted: bool = False   # بلغ حد الخطوات دون جواب نهائي

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
    for _ in range(max_steps):
        prompt = REACT_INSTRUCTIONS.format(
            tools=registry.describe(), task=task, scratchpad=scratchpad
        )
        text = llm_call(prompt) or ""

        final = _FINAL_RE.search(text)
        if final:
            result.final_answer = final.group(1).strip()
            result.steps.append(ReActStep(_parse_thought(text), None, None, None))
            return result

        m = _ACTION_RE.search(text)
        if not m:
            # النموذج لم يلتزم النسق — أوقف الحلقة (يتكفّل النادِي بمسار احتياطي).
            result.steps.append(ReActStep(_parse_thought(text), None, None, None))
            result.exhausted = True
            return result

        action, action_input = m.group(1).strip(), m.group(2).strip()
        try:
            observation = registry.run(action, action_input)
        except ToolError as e:
            observation = f"خطأ أداة: {e}"
        result.steps.append(ReActStep(_parse_thought(text), action, action_input, observation))
        scratchpad += (
            f"Thought: {_parse_thought(text)}\nAction: {action}\n"
            f"Action Input: {action_input}\nObservation: {observation}\n"
        )
    result.exhausted = True
    return result
