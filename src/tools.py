"""أدوات حقيقية يستدعيها الوكيل (البند 1: Tool Use).

أداتان تعملان فعليًا، لا مخرجات مبرمجة:
- `policy_lookup`: بحث دلالي في سياسات ChromaDB (يحوّل استرجاعنا من «الكود
  يستدعيه» إلى «الوكيل يقرره»).
- `calculator`: حاسبة حسابية/مقارنة يتحقق بها الوكيل من تجاوز المبالغ للحدود.

الحاسبة تُقيَّم بمحلّل AST مقيَّد (لا `eval`) — قرار أمني في مشروع أمني:
تُسمح الأعداد والعمليات الحسابية والمقارنات فقط، وأي شيء آخر يُرفض.
"""
from __future__ import annotations

import ast
import operator
from dataclasses import dataclass
from typing import Callable

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


@dataclass
class Tool:
    name: str
    description: str
    run: Callable[[str], str]


class ToolRegistry:
    """سجل أدوات — يصف الأدوات للوكيل وينفّذ ما يطلبه."""

    def __init__(self, tools: list[Tool]):
        self._tools = {t.name: t for t in tools}

    @property
    def names(self) -> list[str]:
        return list(self._tools)

    def describe(self) -> str:
        return "\n".join(f"- {t.name}(input): {t.description}" for t in self._tools.values())

    def run(self, name: str, tool_input: str) -> str:
        tool = self._tools.get(name)
        if tool is None:
            raise ToolError(f"أداة غير معروفة: {name}. المتاح: {self.names}")
        return tool.run(tool_input)


def build_default_registry(store: PolicyStore) -> ToolRegistry:
    """يبني سجل الأدوات القياسي: بحث السياسات + الحاسبة."""

    def policy_lookup(query: str) -> str:
        hits = store.retrieve(query, k=2)
        if not hits:
            return "لا سياسة مطابقة."
        return "\n".join(f"{h['policy_id']}: {h['text'][:200]}" for h in hits)

    return ToolRegistry([
        Tool("policy_lookup", "يبحث في سياسات المشتريات المؤسسية ويعيد أقرب سياستين", policy_lookup),
        Tool("calculator", "يحسب تعبيرًا رقميًا أو مقارنة مثل '320000 > 300000'", calculator),
    ])
