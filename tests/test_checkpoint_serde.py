"""تحصين فك تسلسل الcheckpoint بقائمة سماح (بند 4 أمن + بند 5 استمرارية).

مَن يكتب في قاعدة الحالة يوجّه ما يُبنى من كائنات عند الاستئناف. المُسلسِل
الافتراضي متساهل، فنقيّده بأنواع المشروع وحدها.
"""
import warnings

from pydantic import BaseModel

from src.checkpointing import ALLOWED_STATE_TYPES, strict_serializer
from src.schemas import AuditEvent, DocType, ExtractedFields, PolicyVerdict, Verdict


class Foreign(BaseModel):
    """نوع خارج المشروع — يمثّل ما قد يزرعه مهاجم في قاعدة الحالة."""

    cmd: str = "rm -rf /"


def test_project_types_survive_a_round_trip():
    """التقييد لا يكسر الاستئناف: كل أنواع الحالة تعود كما هي."""
    serde = strict_serializer()
    payload = {
        "verdict": PolicyVerdict(verdict=Verdict.VIOLATION, cited_policy_id="POL-003", reason="ر"),
        "fields": ExtractedFields(party="س", amount_sar=320000.0),
        "trail": [AuditEvent(node="policy_check", summary="حكم")],
        "type": DocType.INVOICE,
    }
    back = serde.loads_typed(serde.dumps_typed(payload))
    assert back["verdict"].cited_policy_id == "POL-003"
    assert back["fields"].amount_sar == 320000.0
    assert back["trail"][0].digest() == payload["trail"][0].digest()
    assert back["type"] == DocType.INVOICE


def test_foreign_type_is_not_reconstructed():
    """نوع خارج قائمة السماح لا يُبنى — يعود بيانات خاملة لا كائنًا."""
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        lax = JsonPlusSerializer()          # الافتراضي المتساهل
        blob = lax.dumps_typed({"f": Foreign()})
        assert isinstance(lax.loads_typed(blob)["f"], Foreign)   # يبنيه فعلًا

    restored = strict_serializer().loads_typed(blob)["f"]
    assert not isinstance(restored, Foreign)
    assert restored == {"cmd": "rm -rf /"}


def test_allow_list_is_explicit_not_permissive():
    """القائمة معلنة صراحةً — لا `True` تعني «اقبل كل شيء»."""
    allowed = strict_serializer()._allowed_msgpack_modules
    assert allowed is not True
    assert ("src.schemas", "AuditEvent") in allowed
    assert len(allowed) == len(ALLOWED_STATE_TYPES)
