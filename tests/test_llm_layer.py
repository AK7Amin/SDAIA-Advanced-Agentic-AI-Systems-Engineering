"""M2: طبقة LLM — عداد التكلفة/الكمون + fallback المفتاح الثاني (بند rubric 5)."""
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from src.llm import LLMLayer, UsageMeter


def test_meter_accumulates_per_call():
    meter = UsageMeter()
    meter.record(node="classify", prompt_tokens=100, completion_tokens=50, latency_ms=800)
    meter.record(node="extract", prompt_tokens=200, completion_tokens=80, latency_ms=1200)
    assert meter.total_tokens == 430
    assert meter.per_node["classify"]["calls"] == 1
    assert meter.total_latency_ms == 2000


def test_meter_snapshot_serializable():
    meter = UsageMeter()
    meter.record(node="classify", prompt_tokens=10, completion_tokens=5, latency_ms=100)
    snap = meter.snapshot()
    assert isinstance(snap, dict) and "total_tokens" in snap


class _Boom403(Exception):
    status_code = 403


def test_fallback_switches_key_on_403():
    """درس ذاكرة الجمعية: 403 (total limit) يجب أن يحوّل للمفتاح الاحتياطي مثل 402."""
    primary = MagicMock(side_effect=_Boom403("Key limit exceeded"))
    fallback = MagicMock(return_value="ok")
    layer = LLMLayer.__new__(LLMLayer)
    with patch.object(LLMLayer, "_call_primary", primary), patch.object(
        LLMLayer, "_call_fallback", fallback
    ):
        out = LLMLayer.invoke_with_fallback(layer, "prompt")
    assert out == "ok"
    fallback.assert_called_once()


def test_429_also_triggers_fallback_key():
    """429 (تجاوز معدل) يجب أن يدوّر للمفتاح الاحتياطي مثل 402/403.

    رُصد حيًا على الحد اليومي للنماذج المجانية — كان يفشل بلا تدوير.
    """
    layer = LLMLayer.__new__(LLMLayer)
    err = urllib.error.HTTPError("u", 429, "Too Many Requests", {}, None)
    assert LLMLayer._is_quota_error(err) is True


def test_non_quota_error_does_not_rotate():
    """خطأ غير متعلق بالحصة (500) لا يستهلك المفتاح الاحتياطي."""
    err = urllib.error.HTTPError("u", 500, "Server Error", {}, None)
    assert LLMLayer._is_quota_error(err) is False


def test_no_key_in_repr():
    """لا يتسرب المفتاح في أي تمثيل نصي (قاعدة الأمان)."""
    layer = LLMLayer(api_key="sk-or-SECRET", fallback_key="sk-or-SECRET2", model="m")
    assert "SECRET" not in repr(layer) and "SECRET" not in str(layer)
