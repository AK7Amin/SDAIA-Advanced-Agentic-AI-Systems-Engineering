"""محمّل الوثائق — استخراج نص حقيقي من PDF مع تطبيع تشوهات العربية.

بُني على درس موثق من مشروع v3 (مهارة `arabic_pdf_extraction_fixer`):
**لا تستعمل `arabic_reshaper` ولا `bidi` قبل تمرير النص للنموذج** — فهما
للعرض البشري، وتمريرهما يعكس الكلمات منطقيًا ويدمّر فهم النموذج.

ما نفعله بدله (مقيس بسبايك فعلي على ملفات مولَّدة):
1. استخراج خام بـ`pypdf`.
2. **NFKC**: يحوّل صيغ العرض presentation forms (`ﻋﻘﺪ`) إلى حروف عادية (`عقد`).
3. تحويل الأرقام العربية-الهندية (`٣٠٠٠٠`) إلى لاتينية.
4. إصلاح التواريخ المقلوبة (`01-08-2026` ← `2026-08-01`) — أثر معروف لاختلاط
   الاتجاهين RTL/LTR داخل السطر.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from pypdf import PdfReader

_ARABIC_INDIC = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
#: تاريخ بصيغة DD-MM-YYYY (سنة من أربع خانات في الآخر) = مقلوب عن ISO.
_REVERSED_DATE = re.compile(r"\b(\d{2})-(\d{2})-(\d{4})\b")


def normalize_arabic_pdf_text(text: str) -> str:
    """يطبّع نصًا مستخرجًا من PDF عربي إلى شكل منطقي صالح للنموذج."""
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(_ARABIC_INDIC)
    text = _REVERSED_DATE.sub(lambda m: f"{m.group(3)}-{m.group(2)}-{m.group(1)}", text)
    return text


def extract_pdf_text(path: str | Path) -> str:
    """يستخرج نص كل صفحات PDF ويطبّعه."""
    reader = PdfReader(str(path))
    pages = [(p.extract_text() or "") for p in reader.pages]
    return normalize_arabic_pdf_text("\n".join(pages)).strip()


def load_document(path: str | Path) -> str:
    """يقرأ وثيقة: PDF حقيقي أو نصًا عاديًا — واجهة واحدة للأنبوب."""
    p = Path(path)
    if p.suffix.lower() == ".pdf":
        return extract_pdf_text(p)
    return p.read_text(encoding="utf-8")
