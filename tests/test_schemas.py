"""M1: عقود الرسائل بين الوكلاء — typed outputs (بند rubric 2)."""
import pytest
from pydantic import ValidationError

from src.schemas import (
    AuditEvent,
    Classification,
    DocType,
    ExtractedFields,
    PolicyVerdict,
    Verdict,
)


def test_doc_types_are_closed_set():
    assert {d.value for d in DocType} == {"contract", "invoice", "letter", "unknown"}


def test_classification_requires_confidence_in_range():
    Classification(doc_type=DocType.CONTRACT, confidence=0.9, rationale="بنود عقد واضحة")
    with pytest.raises(ValidationError):
        Classification(doc_type=DocType.CONTRACT, confidence=1.7, rationale="x")


def test_extracted_fields_amount_must_be_positive():
    ExtractedFields(party="شركة التقنية", amount_sar=30000, duration_months=12)
    with pytest.raises(ValidationError):
        ExtractedFields(party="x", amount_sar=-5, duration_months=1)


def test_extracted_fields_tracks_missing():
    f = ExtractedFields(party="شركة التقنية", amount_sar=None, duration_months=12)
    assert "amount_sar" in f.missing_fields()


def test_verdict_is_three_valued():
    assert {v.value for v in Verdict} == {"compliant", "violation", "uncertain"}


def test_policy_verdict_must_cite_policy_when_violation():
    with pytest.raises(ValidationError):
        PolicyVerdict(verdict=Verdict.VIOLATION, cited_policy_id=None, reason="تجاوز")
    PolicyVerdict(verdict=Verdict.VIOLATION, cited_policy_id="POL-003", reason="تجاوز الحد")


def test_audit_event_is_immutable():
    e = AuditEvent(node="classify", summary="صُنفت عقدًا", cost_usd=0.0, latency_ms=12)
    with pytest.raises(ValidationError):
        e.summary = "تعديل"
