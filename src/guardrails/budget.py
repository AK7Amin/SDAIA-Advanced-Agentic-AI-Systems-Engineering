"""حاجزا الميزانية والحجم — يمنعان انفجار التكلفة واستنزاف الموارد (يوم 5).

- BudgetGuard: حد لعدد نداءات النموذج لكل وثيقة، يفشل بصوت عالٍ عند التجاوز.
- حد حجم المدخل: يُفحص **قبل** أي regex/تقنيع (يمنع ReDoS واستهلاك الذاكرة).
"""
from __future__ import annotations

MAX_INPUT_CHARS = 20_000


class BudgetExceeded(RuntimeError):
    """يُرفع عند تجاوز حد نداءات النموذج لوثيقة واحدة."""


class InputTooLarge(ValueError):
    """يُرفع عند تجاوز الوثيقة حد الحجم قبل المعالجة."""


class BudgetGuard:
    def __init__(self, max_calls: int = 8):
        self.max_calls = max_calls
        self._calls = 0

    def charge(self) -> None:
        self._calls += 1
        if self._calls > self.max_calls:
            raise BudgetExceeded(
                f"تجاوز حد النداءات ({self.max_calls}) لوثيقة واحدة — إيقاف لمنع انفجار التكلفة"
            )

    @property
    def calls(self) -> int:
        return self._calls


def enforce_input_size(text: str, limit: int = MAX_INPUT_CHARS) -> None:
    if len(text) > limit:
        raise InputTooLarge(f"حجم المدخل {len(text)} يتجاوز الحد {limit} — رُفض قبل الفحص")
