"""حاجز اجتياز المسار — يمنع doc_id/اسم ملف من الكتابة خارج مجلد المشروع.

يُسقط مباشرةً قاعدة CLAUDE.md: لا كتابة خارج مجلد المشروع أبدًا. المعرّفات
تُطهَّر قبل استخدامها في thread_id أو أسماء ملفات الأرشيف/التقارير.
"""
from __future__ import annotations

import re
from pathlib import Path


class PathTraversalError(ValueError):
    """يُرفع عند محاولة معرّف الخروج من المجلد المسموح."""


_SAFE = re.compile(r"[^A-Za-z0-9_؀-ۿ.-]")


def safe_doc_id(raw: str) -> str:
    """يطهّر معرّف وثيقة: يمنع مكوّنات المسار و`..` والفواصل."""
    if raw is None or not str(raw).strip():
        raise PathTraversalError("معرّف فارغ")
    candidate = str(raw)
    if "/" in candidate or "\\" in candidate or ".." in candidate or "\x00" in candidate:
        raise PathTraversalError(f"معرّف يحوي مكوّن مسار: {candidate!r}")
    cleaned = _SAFE.sub("_", candidate)
    if cleaned in (".", ".."):
        raise PathTraversalError(f"معرّف غير مسموح: {candidate!r}")
    return cleaned


def resolve_within(base_dir: Path, name: str) -> Path:
    """يحل مسارًا ويؤكد أنه داخل base_dir فعليًا (دفاع ثانٍ بعد التطهير)."""
    base = Path(base_dir).resolve()
    target = (base / safe_doc_id(name)).resolve()
    if base != target and base not in target.parents:
        raise PathTraversalError(f"المسار يخرج من المجلد المسموح: {target}")
    return target
