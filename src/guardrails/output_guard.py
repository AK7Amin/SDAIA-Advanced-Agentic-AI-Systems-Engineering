"""حواجز المخرجات — تقنيع PII قبل عرض أي نص للمستخدم أو كتابته في إشعار/سجل.

يوافق قاعدة R021: الهويات والآيبان لا تظهر في المخرجات. المبالغ ليست PII
فلا تُقنَّع (تجنّب الإفراط في التقنيع الذي يفسد الحقول المستخرجة).
"""
from __future__ import annotations

import re

# هوية سعودية: تبدأ بـ1 أو 2، عشر خانات بالضبط، بحدود كلمة (لا تلتقط أرقام 5 خانات).
_SAUDI_ID = re.compile(r"(?<!\d)[12]\d{9}(?!\d)")
# آيبان سعودي: SA + 22 خانة.
_IBAN = re.compile(r"\bSA\d{22}\b", re.IGNORECASE)
# جوال سعودي: 05 + 8 خانات، أو بصيغة +9665.
_MOBILE = re.compile(r"(?<!\d)(?:05\d{8}|\+9665\d{8})(?!\d)")


def mask_pii(text: str) -> str:
    """يقنّع الهوية والآيبان والجوال؛ يُبقي المبالغ وأرقام الفواتير."""
    text = _IBAN.sub("SA**REDACTED**", text)
    text = _SAUDI_ID.sub("**ID-REDACTED**", text)
    text = _MOBILE.sub("**PHONE-REDACTED**", text)
    return text
