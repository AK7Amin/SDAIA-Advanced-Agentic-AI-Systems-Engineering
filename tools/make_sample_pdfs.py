"""أداة تطوير: تولّد عقود PDF عربية اصطناعية لعينات الاختبار.

ليست من تبعيات التشغيل — التشغيل يحتاج `pypdf` فقط للقراءة. هذه الأداة تحتاج
`reportlab arabic-reshaper python-bidi` وتُشغَّل مرة واحدة لتوليد العينات.

قرارات مقيسة بسبايك (لماذا هكذا وليس بسذاجة):
- الرسم يستعمل reshaper+bidi **للعرض البصري فقط داخل الـPDF** (هكذا تُنتَج
  ملفات العربية الحقيقية من Word وغيره) — والقراءة لاحقًا خام بلا عكس.
- الأرقام تُكتب عربية-هندية: مزج الأرقام اللاتينية مع العربية في سطر واحد
  **يُسقط الأرقام كليًا** من الاستخراج (تحقق مباشر).
- مقاطع الأرقام تُعاد لاتجاهها بعد bidi وإلا خرجت مقلوبة (30000 ← 00003).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

FONT_CANDIDATES = ["C:/Windows/Fonts/tahoma.ttf", "C:/Windows/Fonts/arial.ttf"]
_TO_ARABIC_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")
_NUM_RUN = re.compile(r"[\d٠-٩][\d٠-٩\-/,.]*")

DOCS: dict[str, list[str]] = {
    "06_contract_pdf_compliant": [
        "عقد توريد أجهزة حاسوب",
        "الطرف الأول: جمعية المحتوى",
        "الطرف الثاني: شركة الأفق للتقنية",
        "قيمة العقد: 45000 ريال",
        "مدة العقد: 12 شهرًا",
        "تاريخ التوقيع: 2026-07-15",
        "تخضع هذه الاتفاقية لسياسات المشتريات المعتمدة.",
    ],
    "07_contract_pdf_over_limit": [
        "عقد صيانة سنوي",
        "الطرف الأول: جمعية المحتوى",
        "الطرف الثاني: مؤسسة الإمداد الشامل",
        "قيمة العقد: 320000 ريال",
        "مدة العقد: 36 شهرًا",
        "تاريخ التوقيع: 2026-06-01",
        "يشمل العقد الصيانة الوقائية والطارئة.",
    ],
}


def _register_font() -> str:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            pdfmetrics.registerFont(TTFont("ArabicFont", path))
            return "ArabicFont"
    raise SystemExit("لم يُعثر على خط عربي (tahoma/arial)")


def _visual(line: str) -> str:
    """يحوّل سطرًا منطقيًا إلى تمثيله البصري داخل الـPDF."""
    shaped = get_display(arabic_reshaper.reshape(line.translate(_TO_ARABIC_DIGITS)))
    # bidi يعكس المقاطع الرقمية أيضًا — أعِدها لاتجاهها.
    return _NUM_RUN.sub(lambda m: m.group()[::-1], shaped)


def build(out_dir: Path) -> list[Path]:
    font = _register_font()
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, lines in DOCS.items():
        path = out_dir / f"{name}.pdf"
        c = canvas.Canvas(str(path), pagesize=A4)
        c.setFont(font, 15)
        y = 780
        for line in lines:
            c.drawString(60, y, _visual(line))
            y -= 32
        c.save()
        written.append(path)
    return written


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent / "sample_docs"
    for p in build(target):
        print("wrote:", p)
