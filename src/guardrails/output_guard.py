"""حواجز المخرجات — تقنيع PII قبل عرض أي نص للمستخدم أو كتابته في إشعار/سجل.

يوافق قاعدة R021: الهويات والآيبان لا تظهر في المخرجات. المبالغ ليست PII
فلا تُقنَّع (تجنّب الإفراط في التقنيع الذي يفسد الحقول المستخرجة).

**درس مكلف**: الأنماط كانت تبدأ بمحارف ASCII حرفية (`[12]` و`05`) بينما بقيتها
`\\d` التي تطابق يونيكود. فهوية مكتوبة بالأرقام العربية-الهندية «١٠٢٣٤٥٦٧٨٩»
كانت تمر **بلا تقنيع** — في مشروع كل وثائقه عربية. الكشف يقع الآن على نسخة
مُطبَّعة، والتقنيع على النص الأصلي بنفس المواضع (الترجمة محرف بمحرف فتتطابق
الفهارس)، فلا يُشوَّه نص الوثيقة ولا تفلت هوية.
"""
from __future__ import annotations

import re

# هوية سعودية: تبدأ بـ1 أو 2، عشر خانات بالضبط، بحدود كلمة (لا تلتقط أرقام 5 خانات).
_SAUDI_ID = re.compile(r"(?<!\d)[12]\d{9}(?!\d)")
# آيبان سعودي: SA + 22 خانة.
_IBAN = re.compile(r"\bSA\d{22}\b", re.IGNORECASE)
# جوال سعودي: 05 + 8 خانات، أو بصيغة +9665.
_MOBILE = re.compile(r"(?<!\d)(?:05\d{8}|\+9665\d{8})(?!\d)")

#: أرقام عربية-هندية (٠-٩) وفارسية (۰-۹) ← لاتينية. ترجمة محرف بمحرف: الطول
#: والفهارس محفوظة، فما يُكشف في النسخة المطبَّعة يُقنَّع في الأصل بموضعه.
_DIGIT_MAP = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")

_PATTERNS = (
    (_IBAN, "SA**REDACTED**"),
    (_SAUDI_ID, "**ID-REDACTED**"),
    (_MOBILE, "**PHONE-REDACTED**"),
)


def normalize_digits(text: str) -> str:
    """يحوّل الأرقام العربية-الهندية والفارسية إلى لاتينية بلا تغيير الطول."""
    return text.translate(_DIGIT_MAP)


def mask_pii(text: str) -> str:
    """يقنّع الهوية والآيبان والجوال؛ يُبقي المبالغ وأرقام الفواتير.

    يعمل على أي رسم للأرقام (لاتيني/عربي-هندي/فارسي).
    """
    if not text:
        return text
    probe = normalize_digits(text)
    spans: list[tuple[int, int, str]] = []
    for rx, repl in _PATTERNS:
        spans.extend((m.start(), m.end(), repl) for m in rx.finditer(probe))
    if not spans:
        return text
    out, cursor, last_end = [], 0, -1
    for start, end, repl in sorted(spans):
        if start < last_end:      # تداخل: النمط الأسبق (الأطول عادةً) يفوز
            continue
        out.append(text[cursor:start])
        out.append(repl)
        cursor, last_end = end, end
    out.append(text[cursor:])
    return "".join(out)
