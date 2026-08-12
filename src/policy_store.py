"""مخزن السياسات المتجهي — ChromaDB بمضمِّن **محلي مثبت** (نقد B8).

قرار أمني: المضمِّن محلي (لا شبكة) فلا يُرسَل نص أي سياسة/وثيقة خارج الجهاز
(قاعدة R021). حاجز ثقة (نقد B4 تسميم السياسات): يُفهرس فقط ما في مجلد
`policies/` الموثوق — لا نص وثائق واردة إطلاقًا.
"""
from __future__ import annotations

import re
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

_LOCAL_EMBEDDER = embedding_functions.DefaultEmbeddingFunction()  # ONNX MiniLM محلي


def _split_policies(text: str) -> list[tuple[str, str]]:
    """يقسم ملف السياسات إلى (POL-ID، نص) لكل قسم `## POL-XXX ...`."""
    out = []
    blocks = re.split(r"\n(?=##\s*POL-)", text)
    for b in blocks:
        m = re.search(r"POL-\d+", b)
        if m:
            out.append((m.group(0), b.strip()))
    return out


class PolicyStore:
    def __init__(self, persist_dir: str | None = None):
        # عميل في-الذاكرة افتراضًا (اختبارات نظيفة)؛ دائم عند تمرير مسار.
        self._client = (
            chromadb.PersistentClient(path=persist_dir) if persist_dir else chromadb.EphemeralClient()
        )
        self._col = self._client.get_or_create_collection(
            name="policies", embedding_function=_LOCAL_EMBEDDER
        )

    def index_policy_file(self, path: str | Path) -> int:
        """يفهرس ملف سياسات موثوق فقط. يعيد عدد السياسات المفهرسة."""
        text = Path(path).read_text(encoding="utf-8")
        items = _split_policies(text)
        if not items:
            return 0
        self._col.upsert(
            ids=[pid for pid, _ in items],
            documents=[body for _, body in items],
            metadatas=[{"policy_id": pid, "source": str(path)} for pid, _ in items],
        )
        return len(items)

    def known_ids(self) -> set[str]:
        """معرّفات السياسات المفهرسة فعلًا — مرجع التحقق من صدق الاستشهاد."""
        return set(self._col.get(include=[]).get("ids", []))

    def retrieve(self, query: str, k: int = 3) -> list[dict]:
        """يسترجع أقرب السياسات لبنود الوثيقة (بحث دلالي)."""
        res = self._col.query(query_texts=[query], n_results=k)
        docs = res.get("documents", [[]])[0]
        ids = res.get("ids", [[]])[0]
        return [{"policy_id": i, "text": d} for i, d in zip(ids, docs)]
