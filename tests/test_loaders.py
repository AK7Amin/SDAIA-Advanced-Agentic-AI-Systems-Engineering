"""استخراج PDF حقيقي + تطبيع تشوهات العربية (يغلق «الاستيعاب محاكاة»).

يعمل على ملفات PDF فعلية في `sample_docs/` مولَّدة بـ`tools/make_sample_pdfs.py`.
"""
from pathlib import Path

import pytest

from src.loaders import extract_pdf_text, load_document, normalize_arabic_pdf_text

PDF = Path(__file__).parent.parent / "sample_docs" / "06_contract_pdf_compliant.pdf"


class TestNormalizer:
    def test_presentation_forms_become_normal_arabic(self):
        """NFKC يحوّل صيغ العرض التي يخرجها الـPDF إلى حروف عادية."""
        assert normalize_arabic_pdf_text("ﻋﻘﺪ ﺗﻮﺭﻳﺪ") == "عقد توريد"

    def test_arabic_indic_digits_become_latin(self):
        assert "45000" in normalize_arabic_pdf_text("قيمة العقد: ٤٥٠٠٠ ريال")

    def test_reversed_date_is_repaired(self):
        """أثر معروف لاختلاط RTL/LTR: التاريخ يخرج مقلوب المقاطع."""
        assert normalize_arabic_pdf_text("تاريخ التوقيع: 15-07-2026").endswith("2026-07-15")

    def test_iso_date_left_untouched(self):
        assert normalize_arabic_pdf_text("2026-07-15").strip() == "2026-07-15"

    def test_plain_amount_not_mangled(self):
        assert "45000" in normalize_arabic_pdf_text("45000 ريال")


@pytest.mark.skipif(not PDF.exists(), reason="عيّنة الـPDF غير مولَّدة")
class TestRealPdf:
    def test_extracts_all_business_fields(self):
        """القيم التي يحتاجها وكيل الاستخراج تصل سليمة من ملف PDF حقيقي."""
        text = extract_pdf_text(PDF)
        assert "45000" in text            # القيمة
        assert "2026-07-15" in text       # التاريخ بصيغته الصحيحة
        assert "12" in text               # المدة
        assert "شركة الأفق للتقنية" in text  # الطرف الثاني

    def test_no_presentation_forms_leak_through(self):
        text = extract_pdf_text(PDF)
        assert "ﻋ" not in text and "ﺍ" not in text

    def test_load_document_dispatches_by_suffix(self, tmp_path):
        assert "45000" in load_document(PDF)
        txt = tmp_path / "a.md"
        txt.write_text("نص عادي", encoding="utf-8")
        assert load_document(txt) == "نص عادي"
