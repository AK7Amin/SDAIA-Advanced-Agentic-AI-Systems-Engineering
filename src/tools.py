"""واجهة أدوات بنمط MCP = Model Context Protocol (البند 1: Tool Use).

الرُبرِك يطلب استدعاء أدوات حقيقية **عبر function calling أو واجهة أدوات
بنمط MCP**. فالأداة هنا ليست دالة بايثون حرة، بل **عقد معلن**:

1. **إعلان**: لكل أداة `inputSchema` بصيغة JSON Schema — نفس الحقول التي
   يعيدها `tools/list` في MCP (`name` / `description` / `inputSchema`).
2. **استدعاء منظَّم**: `ToolCall(name, arguments)` — كائن متحقق منه، لا نص حر.
   تحليل نص النموذج يقع في `parse_call` وحدها (حدّ واحد بين النص والعقد).
3. **موزِّع واحد**: كل تنفيذ يمر بـ`dispatch` — يتحقق من الاسم والوسائط
   (مفقودة/زائدة/نوع خاطئ) قبل أن يلمس أي كود أداة.
4. **سجل تنفيذ**: كل نداء يُقيَّد في `execution_log` بوسائطه ونتيجته وزمنه —
   دليل «استدعاءات أدوات حقيقية» قابل للتفتيش بعد التشغيل.

الحاسبة تُقيَّم بمحلّل AST مقيَّد (لا `eval`) — قرار أمني في مشروع أمني:
تُسمح الأعداد والعمليات الحسابية والمقارنات فقط، وأي شيء آخر يُرفض.
"""
from __future__ import annotations

import ast
import inspect
import json
import operator
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from src.policy_store import PolicyStore

_ALLOWED_BINOP = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Mod: operator.mod, ast.Pow: operator.pow,
}
_ALLOWED_CMP = {
    ast.Gt: operator.gt, ast.Lt: operator.lt, ast.GtE: operator.ge,
    ast.LtE: operator.le, ast.Eq: operator.eq, ast.NotEq: operator.ne,
}


class ToolError(ValueError):
    """خطأ استخدام أداة — يُعاد للوكيل كملاحظة observation."""


def _safe_eval(node: ast.AST):
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ToolError("ثابت غير مسموح")
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        v = _safe_eval(node.operand)
        return +v if isinstance(node.op, ast.UAdd) else -v
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BINOP:
        return _ALLOWED_BINOP[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.Compare) and len(node.ops) == 1 and type(node.ops[0]) in _ALLOWED_CMP:
        return _ALLOWED_CMP[type(node.ops[0])](_safe_eval(node.left), _safe_eval(node.comparators[0]))
    raise ToolError("تعبير غير مسموح — تُقبل الأعداد والحساب والمقارنة فقط")


def calculator(expression: str) -> str:
    """يقيّم تعبيرًا حسابيًا أو مقارنة. مثال: '320000 > 300000' → 'True'."""
    try:
        tree = ast.parse(str(expression).strip(), mode="eval")
    except SyntaxError:
        raise ToolError(f"تعبير غير صالح: {expression!r}") from None
    return str(_safe_eval(tree))


# ---------------------------------------------------------------- العقود

@dataclass(frozen=True)
class ToolCall:
    """طلب استدعاء **منظَّم**: اسم الأداة + وسائط مُسمّاة (لا سلسلة حرة)."""

    name: str
    arguments: dict[str, Any]

    def render(self) -> str:
        return f"{self.name}({json.dumps(self.arguments, ensure_ascii=False)})"


@dataclass(frozen=True)
class ToolResult:
    """نتيجة تنفيذ مقيَّدة في سجل التنفيذ (دليل قابل للتفتيش)."""

    name: str
    arguments: dict[str, Any]
    ok: bool
    output: str
    latency_ms: int

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "arguments": self.arguments,
            "ok": self.ok,
            "output": self.output[:200],
            "latency_ms": self.latency_ms,
        }


def _schema_from_signature(fn: Callable) -> dict:
    """مخطط JSON افتراضي مستنتج من توقيع الدالة — كل وسيط نصي ومطلوب."""
    params = [p for p in inspect.signature(fn).parameters]
    return {
        "type": "object",
        "properties": {p: {"type": "string"} for p in params},
        "required": list(params),
    }


@dataclass
class Tool:
    """أداة معلنة بنمط MCP: اسم + وصف + مخطط مدخلات JSON Schema."""

    name: str
    description: str
    run: Callable[..., str]
    input_schema: dict = field(default=None)  # type: ignore[assignment]

    def __post_init__(self):
        if not self.input_schema:
            self.input_schema = _schema_from_signature(self.run)

    @property
    def properties(self) -> dict:
        return self.input_schema.get("properties", {})

    @property
    def required(self) -> list[str]:
        return list(self.input_schema.get("required", list(self.properties)))

    def descriptor(self) -> dict:
        """نفس شكل عنصر `tools/list` في MCP."""
        return {"name": self.name, "description": self.description, "inputSchema": self.input_schema}


_TYPE_CHECKS = {
    "string": lambda v: isinstance(v, str),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
}


class ToolRegistry:
    """سجل أدوات بنمط MCP: يعلن الأدوات، ويتحقق من كل استدعاء، ويسجّله."""

    def __init__(self, tools: list[Tool]):
        self._tools = {t.name: t for t in tools}
        #: سجل التنفيذ — كل استدعاء نُفِّذ فعلًا (دليل البند 1).
        self.execution_log: list[ToolResult] = []

    @property
    def names(self) -> list[str]:
        return list(self._tools)

    def list_tools(self) -> list[dict]:
        """إعلان الأدوات — مكافئ `tools/list` في MCP."""
        return [t.descriptor() for t in self._tools.values()]

    def describe(self) -> str:
        """وصف نصي للمطالبة، يعرض المخطط ليولّد النموذج وسائط مسماة."""
        lines = []
        for t in self._tools.values():
            args = ", ".join(
                f"{k}: {v.get('type', 'string')}" for k, v in t.properties.items()
            )
            lines.append(f"- {t.name}({args}): {t.description}")
        return "\n".join(lines)

    # ------------------------------------------------------- التحليل والتوزيع

    def parse_call(self, name: str, raw_input: str) -> ToolCall:
        """يحوّل مخرج النموذج النصي إلى `ToolCall` منظَّم.

        يقبل شكلين: كائن JSON بوسائط مسماة (المفضّل، وهو ما تطلبه المطالبة)،
        أو قيمة مفردة تُسنَد للوسيط المطلوب الوحيد (تسامح مع النماذج الصغيرة).
        الحد بين «نص النموذج» و«العقد» يقع هنا وحده.
        """
        tool = self._tools.get(name)
        if tool is None:
            raise ToolError(f"أداة غير معروفة: {name}. المتاح: {self.names}")
        raw = (raw_input or "").strip()
        if raw.startswith("{"):
            try:
                data = json.loads(raw)
                if isinstance(data, dict):
                    return ToolCall(name=name, arguments=data)
            except json.JSONDecodeError:
                pass
        required = tool.required
        if len(required) != 1:
            raise ToolError(
                f"{name} يحتاج وسائط مسماة بصيغة JSON: {json.dumps(tool.input_schema, ensure_ascii=False)}"
            )
        return ToolCall(name=name, arguments={required[0]: raw})

    def validate(self, call: ToolCall) -> Tool:
        """يتحقق من الاسم والوسائط ضد المخطط — قبل تنفيذ أي كود أداة."""
        tool = self._tools.get(call.name)
        if tool is None:
            raise ToolError(f"أداة غير معروفة: {call.name}. المتاح: {self.names}")
        missing = [k for k in tool.required if k not in call.arguments]
        if missing:
            raise ToolError(f"وسائط ناقصة لـ{call.name}: {missing}")
        unknown = [k for k in call.arguments if k not in tool.properties]
        if unknown:
            raise ToolError(f"وسائط غير معروفة لـ{call.name}: {unknown}")
        for key, value in call.arguments.items():
            expected = tool.properties[key].get("type", "string")
            check = _TYPE_CHECKS.get(expected)
            if check and not check(value):
                raise ToolError(f"نوع خاطئ للوسيط {key} في {call.name}: يُتوقع {expected}")
        return tool

    def dispatch(self, call: ToolCall) -> ToolResult:
        """الموزِّع الموحّد: تحقق ← تنفيذ ← قيد في سجل التنفيذ.

        فشل التحقق أو فشل الأداة يُقيَّد أيضًا (`ok=False`) ثم يُرفع `ToolError`
        ليعود للوكيل ملاحظةً — لا يُبتلع الخطأ ولا يُخفى من السجل.
        """
        t0 = time.perf_counter()
        try:
            tool = self.validate(call)
            # ربط **بالاسم** لا بالموضع: مخطط بثلاثة وسائط ووسيطان مطلوبان
            # كان يمرّر الثاني مكان الثالث. `validate` ضمن أن الأسماء صحيحة.
            output = str(tool.run(**call.arguments))
        except ToolError as exc:
            self.execution_log.append(
                ToolResult(call.name, call.arguments, False, f"خطأ أداة: {exc}",
                           int((time.perf_counter() - t0) * 1000))
            )
            raise
        result = ToolResult(
            call.name, call.arguments, True, output, int((time.perf_counter() - t0) * 1000)
        )
        self.execution_log.append(result)
        return result

    def run(self, name: str, tool_input: str) -> str:
        """مسار مختصر لمنادٍ يملك نصًا: يحلّل ثم يوزّع (يمر بنفس التحقق)."""
        return self.dispatch(self.parse_call(name, tool_input)).output


def build_default_registry(store: PolicyStore) -> ToolRegistry:
    """يبني سجل الأدوات القياسي: بحث السياسات + الحاسبة، بمخططات معلنة."""

    def policy_lookup(query: str) -> str:
        hits = store.retrieve(query, k=2)
        if not hits:
            return "لا سياسة مطابقة."
        return "\n".join(f"{h['policy_id']}: {h['text'][:200]}" for h in hits)

    return ToolRegistry([
        Tool(
            "policy_lookup",
            "يبحث دلاليًا في سياسات المشتريات المؤسسية ويعيد أقرب سياستين بمعرّفيهما",
            policy_lookup,
            {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "نص البحث عن السياسة ذات الصلة"}
                },
                "required": ["query"],
            },
        ),
        Tool(
            "calculator",
            "يحسب تعبيرًا رقميًا أو مقارنة مثل '320000 > 100000'",
            calculator,
            {
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "تعبير حسابي أو مقارنة"}
                },
                "required": ["expression"],
            },
        ),
    ])
