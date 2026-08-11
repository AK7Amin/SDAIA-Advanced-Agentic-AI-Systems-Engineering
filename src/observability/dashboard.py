"""مولّد لوحة المراقبة — يقرأ لقطة المقاييس المحفوظة (لا endpoint حي — نقد C2).

ينتج صفحة HTML مستقلة يفتحها المقيّم دون تشغيل شيء. عربية RTL.
"""
from __future__ import annotations

import json
from pathlib import Path


def render(snapshot_path: str | Path, out_path: str | Path) -> Path:
    snap = json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
    per_doc = snap.get("per_doc", {})
    rows = "\n".join(
        f"<tr><td>{d}</td><td>{v['calls']}</td><td>{v['tokens']}</td>"
        f"<td>{v['latency_ms']}</td><td>${v['ref_cost_usd']:.6f}</td></tr>"
        for d, v in per_doc.items()
    )
    html = f"""<!DOCTYPE html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8">
<title>لوحة مراقبة — وكيل دورة حياة الوثيقة</title>
<style>
body{{font-family:'Segoe UI',Tahoma,sans-serif;background:#0f1419;color:#e8e6e1;padding:2rem;line-height:1.7}}
h1{{color:#4fd1c5}} table{{border-collapse:collapse;width:100%;margin-top:1rem}}
th,td{{border:1px solid #333;padding:.5rem .8rem;text-align:right}} th{{background:#1e2126;color:#4fd1c5}}
.cards{{display:flex;gap:1rem;flex-wrap:wrap;margin:1rem 0}}
.card{{background:#1e2126;border-radius:10px;padding:1rem 1.5rem;border-right:3px solid #4fd1c5}}
.card b{{display:block;font-size:1.6rem;color:#4fd1c5}} small{{color:#9a988f}}
</style></head><body>
<h1>لوحة مراقبة الأداء والتكلفة</h1>
<p><small>تُقرأ من لقطة محفوظة metrics-snapshot.json — لا تعتمد على خدمة حية.
التكلفة مرجعية بأسعار gpt-4o-mini (النموذج الفعلي مجاني).</small></p>
<div class="cards">
  <div class="card"><b>{snap.get('total_tokens',0)}</b><small>إجمالي التوكنز</small></div>
  <div class="card"><b>{snap.get('total_latency_ms',0)} م/ث</b><small>إجمالي الكمون</small></div>
  <div class="card"><b>${snap.get('total_ref_cost_usd',0):.4f}</b><small>التكلفة المرجعية</small></div>
  <div class="card"><b>{len(per_doc)}</b><small>وثائق معالَجة</small></div>
</div>
<h2>التكلفة والكمون لكل وثيقة</h2>
<table><tr><th>الوثيقة</th><th>نداءات</th><th>توكنز</th><th>كمون (م/ث)</th><th>تكلفة مرجعية</th></tr>
{rows}
</table>
</body></html>"""
    out = Path(out_path)
    out.write_text(html, encoding="utf-8")
    return out


if __name__ == "__main__":
    import sys

    render(sys.argv[1], sys.argv[2])
    print("dashboard written:", sys.argv[2])
