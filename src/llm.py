"""طبقة النموذج — نداء OpenRouter مع تدوير مفتاحين + عداد استهلاك + تنقيح أسرار.

قرارات مثبتة:
- التدوير عند 402 **و403** (درس ذاكرة الجمعية: 403 = total limit كان لا يُدوّر).
- المفتاح لا يتسرب في repr ولا في أي استثناء (redact_secrets مركزي).
- التسعير مرجعي: النموذج المجاني تكلفته 0، لكن نحسب «كم كان سيكلف» بأسعار
  مرجعية لإظهار هندسة التكلفة لا عمود أصفار (بند rubric 5).
"""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field

_SECRET_RE = re.compile(r"sk-or-[A-Za-z0-9\-_]+")

#: مفاتيح مسجَّلة وقت التشغيل تُمسح حرفيًا من أي نص — يغطي المزودين الذين
#: لا تحمل مفاتيحهم بادئة معروفة (Mistral مثلًا) بعد إتاحة تبديل المزود.
_KNOWN_SECRETS: set[str] = set()


def register_secret(value: str | None) -> None:
    """يسجّل قيمة سرية لتُنقَّح من كل مخرج لاحق (سجل/أثر/رسالة خطأ)."""
    if value and len(value) >= 12:
        _KNOWN_SECRETS.add(value)

# أسعار مرجعية افتراضية (دولار لكل مليون توكن) — بأسلوب gpt-4o-mini.
REF_PRICE_PROMPT = 0.15 / 1_000_000
REF_PRICE_COMPLETION = 0.60 / 1_000_000


def redact_secrets(text: str) -> str:
    """يمسح أي مفتاح مزوّد من نص قبل كتابته في سجل/أثر/رسالة خطأ."""
    out = _SECRET_RE.sub("sk-or-***REDACTED***", str(text))
    for secret in _KNOWN_SECRETS:
        out = out.replace(secret, "***REDACTED***")
    return out


class ProviderError(RuntimeError):
    """خطأ من المزوّد يحمل رمز حالة — يشمل حالة 200 بجسم خطأ."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class UsageMeter:
    """عداد استهلاك لكل عقدة **ولكل وثيقة** (بند rubric 5)."""

    total_tokens: int = 0
    total_latency_ms: int = 0
    total_ref_cost_usd: float = 0.0
    per_node: dict = field(default_factory=dict)
    per_doc: dict = field(default_factory=dict)

    def record(
        self,
        node: str,
        prompt_tokens: int,
        completion_tokens: int,
        latency_ms: int,
        doc_id: str = "-",
    ) -> float:
        tokens = prompt_tokens + completion_tokens
        ref_cost = prompt_tokens * REF_PRICE_PROMPT + completion_tokens * REF_PRICE_COMPLETION
        self.total_tokens += tokens
        self.total_latency_ms += latency_ms
        self.total_ref_cost_usd += ref_cost
        for bucket, key in ((self.per_node, node), (self.per_doc, doc_id)):
            slot = bucket.setdefault(key, {"calls": 0, "tokens": 0, "latency_ms": 0, "ref_cost_usd": 0.0})
            slot["calls"] += 1
            slot["tokens"] += tokens
            slot["latency_ms"] += latency_ms
            slot["ref_cost_usd"] += ref_cost
        return ref_cost

    def snapshot(self) -> dict:
        return {
            "total_tokens": self.total_tokens,
            "total_latency_ms": self.total_latency_ms,
            "total_ref_cost_usd": round(self.total_ref_cost_usd, 6),
            "per_node": self.per_node,
            "per_doc": self.per_doc,
        }


class LLMLayer:
    """غلاف نداء النموذج بمفتاح أساسي واحتياطي وعداد."""

    def __init__(
        self,
        api_key: str | None = None,
        fallback_key: str | None = None,
        model: str | None = None,
        meter: UsageMeter | None = None,
    ):
        # أسماء عامة أولًا (`LLM_API_KEY`) ثم أسماء OpenRouter للتوافق الخلفي —
        # المزوّد صار قابلًا للتبديل فلا يليق أن يحمل المفتاح اسم مزوّد بعينه.
        self._api_key = api_key or os.getenv("LLM_API_KEY") or os.getenv("OPENROUTER_API_KEY", "")
        self._fallback_key = (
            fallback_key
            or os.getenv("LLM_API_KEY_FALLBACK")
            or os.getenv("OPENROUTER_API_KEY_FALLBACK", "")
        )
        self.model = model or os.getenv("LLM_MODEL", "openai/gpt-oss-20b:free")
        #: المزوّد قابل للتبديل بمتغير بيئة واحد — كل المزودين هنا يتكلمون
        #: نفس واجهة OpenAI المتوافقة، فتبديل OpenRouter↔Mistral بلا لمس كود.
        self.base_url = os.getenv(
            "LLM_BASE_URL", "https://openrouter.ai/api/v1/chat/completions"
        )
        register_secret(self._api_key)
        register_secret(self._fallback_key)
        self.meter = meter or UsageMeter()
        #: يُضبط قبل معالجة كل وثيقة ليُنسب الاستهلاك إليها (تكلفة لكل وثيقة).
        self.active_doc_id = "-"
        #: حاجز ميزانية لكل وثيقة — يُستبدل في process_document؛ None = بلا حد.
        self.budget = None

    def __repr__(self) -> str:  # لا يتسرب المفتاح أبدًا
        return f"LLMLayer(model={self.model!r}, key=set={bool(self._api_key)})"

    __str__ = __repr__

    def _post(self, key: str, prompt: str) -> tuple[str, int, int]:
        """نداء HTTP فعلي لـOpenRouter. يُعزل ليسهل ترقيعه في الاختبار."""
        import json
        import urllib.request

        # temperature=0: أخذ عينات حتمي — أول استراتيجية موثوقية في شرائح اليوم 5.
        body = json.dumps(
            {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                # نماذج الاستدلال (مثل gpt-oss) تستهلك مئات التوكنز في reasoning
                # قبل المحتوى؛ حد منخفض يُرجع محتوى **فارغًا** (شُخِّص حيًا).
                "max_tokens": int(os.getenv("LLM_MAX_TOKENS", "2000")),
                "temperature": 0,
            }
        ).encode()
        req = urllib.request.Request(
            self.base_url,
            data=body,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=90) as r:
            resp = json.load(r)
        # المزوّد قد يعيد 200 ومعها جسم خطأ (بلا choices) — خصوصًا عند تحديد
        # المعدل upstream. نحوّلها لخطأ مصنَّف ليعمل التدوير/إعادة المحاولة.
        if "choices" not in resp:
            err = resp.get("error") or {}
            code = err.get("code") or resp.get("code")
            raise ProviderError(
                redact_secrets(str(err.get("message") or resp))[:200], status_code=code
            )
        content = resp["choices"][0]["message"]["content"] or ""
        usage = resp.get("usage", {})
        return content, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)

    # مقابس content-only للاستخدام في invoke_with_fallback (سهلة الترقيع بالاختبار).
    def _call_primary(self, prompt: str) -> str:
        return self._post(self._api_key, prompt)[0]

    def _call_fallback(self, prompt: str) -> str:
        return self._post(self._fallback_key, prompt)[0]

    @staticmethod
    def _status_of(exc: Exception) -> int | None:
        return getattr(exc, "status_code", getattr(exc, "code", None))

    @classmethod
    def _is_quota_error(cls, exc: Exception) -> bool:
        """402 رصيد، 403 حد إجمالي، 429 تجاوز معدل — كلها تستدعي المفتاح الاحتياطي.

        (429 أُضيف بعد رصده حيًا على الحد اليومي للنماذج المجانية.)
        """
        return cls._status_of(exc) in (402, 403, 429)

    def _post_with_retry(self, key: str, prompt: str, attempts: int = 3) -> tuple[str, int, int]:
        """تراجع أسّي exponential backoff على 429 — سياسة إعادة المحاولة (يوم 5)."""
        delay = 2.0
        last: Exception | None = None
        for i in range(attempts):
            try:
                return self._post(key, prompt)
            except Exception as exc:  # noqa: BLE001
                last = exc
                if self._status_of(exc) != 429 or i == attempts - 1:
                    raise
                time.sleep(delay)
                delay *= 2
        raise last  # type: ignore[misc]

    def invoke_with_fallback(self, prompt: str) -> str:
        """ينادي الأساسي؛ عند 402/403 يحوّل للاحتياطي. يُنقّح أي خطأ من الأسرار."""
        try:
            return self._call_primary(prompt)
        except Exception as exc:  # noqa: BLE001
            if self._is_quota_error(exc):
                return self._call_fallback(prompt)
            raise RuntimeError(redact_secrets(str(exc))) from None

    def invoke(self, prompt: str, node: str = "-", doc_id: str = "-") -> str:
        """نداء موقوت مع تسجيل الاستهلاك (توكنز/كمون/تكلفة مرجعية).

        يمر أولًا بحاجز الميزانية: تجاوز الحد لوثيقة واحدة يرفع BudgetExceeded
        بدل الاستمرار في الإنفاق (الجواب العملي على «انفجار التكلفة»).
        """
        if self.budget is not None:
            self.budget.charge()
        t0 = time.perf_counter()
        try:
            content, pt, ct = self._post_with_retry(self._api_key, prompt)
        except Exception as exc:  # noqa: BLE001
            if self._is_quota_error(exc) and self._fallback_key:
                content, pt, ct = self._post_with_retry(self._fallback_key, prompt)
            else:
                raise RuntimeError(redact_secrets(str(exc))) from None
        latency_ms = int((time.perf_counter() - t0) * 1000)
        self.meter.record(
            node=node,
            prompt_tokens=pt,
            completion_tokens=ct,
            latency_ms=latency_ms,
            doc_id=doc_id if doc_id != "-" else self.active_doc_id,
        )
        return content
