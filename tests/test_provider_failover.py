"""التراجع **بين المزودين** لا بين مفتاحين فقط (بند 5: مسار فشل حقيقي).

الحصة المجانية تنفد لدى مزوّد بأكمله، فلا ينفع مفتاح ثانٍ عند نفس المزوّد.
السلسلة: مفاتيح المزوّد الأول بالترتيب ← ثم المزوّد الثاني.
"""
import urllib.error

import pytest

from src.llm import LLMLayer


_ENV_KEYS = (
    "LLM_API_KEY", "LLM_API_KEY_FALLBACK", "LLM_API_KEY_2",
    "LLM_BASE_URL", "LLM_BASE_URL_2", "LLM_MODEL", "LLM_MODEL_2",
    "LLM_PROVIDER_NAME", "LLM_PROVIDER_NAME_2",
    "OPENROUTER_API_KEY", "OPENROUTER_API_KEY_FALLBACK",
)


def _layer(monkeypatch, **env):
    """بيئة معزولة: `.env` الحقيقي يُحمَّل عند استيراد main، فنمسح أثره أولًا."""
    for k in _ENV_KEYS:
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return LLMLayer()


BASE = {
    "LLM_API_KEY": "k1", "LLM_API_KEY_FALLBACK": "k2",
    "LLM_BASE_URL": "https://p1.example/v1/chat", "LLM_MODEL": "m1",
    "LLM_BASE_URL_2": "https://p2.example/v1/chat", "LLM_MODEL_2": "m2",
    "LLM_API_KEY_2": "k3",
}


def _quota(code=429):
    return urllib.error.HTTPError("u", code, "quota", {}, None)


class TestChainConstruction:
    def test_second_provider_joins_the_chain(self, monkeypatch):
        layer = _layer(monkeypatch, **BASE)
        assert [p.name for p in layer.providers] == ["p1.example", "p2.example"]
        assert layer.providers[1].model == "m2"

    def test_chain_has_one_provider_when_second_absent(self, monkeypatch):
        env = {k: v for k, v in BASE.items() if not k.endswith("_2")}
        monkeypatch.delenv("LLM_BASE_URL_2", raising=False)
        monkeypatch.delenv("LLM_API_KEY_2", raising=False)
        layer = _layer(monkeypatch, **env)
        assert len(layer.providers) == 1


class TestFailover:
    def test_exhausted_provider_falls_through_to_the_next(self, monkeypatch):
        """كل مفاتيح المزوّد الأول نفدت ← يخدم الثاني، ويُسجَّل أنه هو من خدم."""
        seen = []

        def fake_post(key, prompt, base_url=None, model=None):
            seen.append((key, base_url))
            if base_url and "p1" in base_url:
                raise _quota()
            return ("جاهز", 5, 3)

        layer = _layer(monkeypatch, **BASE)
        monkeypatch.setattr(layer, "_post", fake_post)
        monkeypatch.setattr("time.sleep", lambda _s: None)     # لا ننتظر التراجع الأسّي
        out = layer.invoke("مهمة", node="classify")
        assert out == "جاهز"
        # 429 يُعاد معه المحاولة على المفتاح نفسه، فنقارن **ترتيب المفاتيح** لا تكرارها.
        order = list(dict.fromkeys(k for k, _ in seen))
        assert order == ["k1", "k2", "k3"]                     # بالترتيب، بلا تخطٍّ
        assert layer.active_provider == "p2.example"
        assert layer.meter.per_provider["p2.example"]["calls"] == 1

    def test_non_quota_failure_does_not_burn_the_chain(self, monkeypatch):
        """عطل حقيقي (500) يُرفع فورًا — لا نستهلك بقية المفاتيح على خطأ ليس حصة."""
        calls = []

        def fake_post(key, prompt, base_url=None, model=None):
            calls.append(key)
            raise urllib.error.HTTPError("u", 500, "boom", {}, None)

        layer = _layer(monkeypatch, **BASE)
        monkeypatch.setattr(layer, "_post", fake_post)
        with pytest.raises(RuntimeError):
            layer.invoke("مهمة")
        assert calls == ["k1"]

    def test_all_providers_exhausted_raises_redacted(self, monkeypatch):
        def fake_post(key, prompt, base_url=None, model=None):
            raise _quota(402)

        layer = _layer(monkeypatch, **BASE)
        monkeypatch.setattr(layer, "_post", fake_post)
        with pytest.raises(RuntimeError) as exc:
            layer.invoke("مهمة")
        assert "k1" not in str(exc.value) and "k3" not in str(exc.value)

    def test_missing_keys_fail_loudly(self, monkeypatch):
        for var in ("LLM_API_KEY", "LLM_API_KEY_FALLBACK", "LLM_API_KEY_2",
                    "OPENROUTER_API_KEY", "OPENROUTER_API_KEY_FALLBACK"):
            monkeypatch.delenv(var, raising=False)
        with pytest.raises(RuntimeError, match="لا مفتاح"):
            LLMLayer().invoke("مهمة")


def test_provider_appears_in_metrics_snapshot(monkeypatch):
    """المقاييس تكشف من خدم فعلًا — وإلا بقي التراجع ادعاءً غير مرئي."""
    layer = _layer(monkeypatch, **BASE)
    monkeypatch.setattr(layer, "_post", lambda *a, **k: ("ok", 1, 1))
    layer.invoke("مهمة", node="extract", doc_id="D1")
    assert "per_provider" in layer.meter.snapshot()
    assert layer.meter.snapshot()["per_provider"]["p1.example"]["calls"] == 1
