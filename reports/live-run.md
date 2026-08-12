# سجل التشغيل الحي — دليل تنفيذي

> مُولّد آليًا بتشغيل فعلي على OpenRouter (نموذج مجاني `openai/gpt-oss-20b:free`)
> من **حالة نظيفة** (حُذفت الcheckpoints والtraces قبل الالتقاط). هذا هو الدليل
> الذي يطلبه نمط التقييم: مخرجات منفَّذة محفوظة، لا مجرد وجود كود.

## 1) معالجة وثائق العينة (الحواجز مفعّلة)
```
== معالجة 5 وثيقة (guardrails=on) ==

  01_contract_compliant.md         → FAILED: RuntimeError: HTTP Error 429: Too Many Requests
  02_invoice_over_limit.md         → FAILED: RuntimeError: HTTP Error 429: Too Many Requests
  03_injected_contract.md          → FAILED: RuntimeError: HTTP Error 429: Too Many Requests
  04_unknown_noise.txt             → quarantined        حواجز={'size_ok': True, 'injection_flagged': False, 'pii_masked': False}
  05_letter.md                     → awaiting_approval  حواجز={'size_ok': True, 'injection_flagged': False, 'pii_masked': False}

لقطة المقاييس: C:\Users\abdul\Desktop\Islamic Content Association\SDAIA Advanced Agentic AI Systems Engineering\capstone-doc-lifecycle\reports\generated\metrics-snapshot.json

```
**القراءة**: عقد مطابق → أُرشف آليًا | فاتورة تتجاوز حد السياسة → توقفت لموافقة
بشرية | وثيقة تحمل حقنًا → عُلِّم الحقن وصُعّدت | ضجيج → حُجر | خطاب → تخطّى
الاستخراج عبر plan_route.

## 2) الاستئناف الحي عبر عملية جديدة (بند الذاكرة/الحالة)
```
استُؤنف 02_invoice_over_limit بقرار «approve» → awaiting_approval

```
⚠️ الاستئناف لم يصل الأرشفة في هذه المحاولة — انظر المخرج أعلاه حرفيًا.

## 3) التكلفة والكمون لكل وثيقة (من metrics-snapshot.json)
| الوثيقة | نداءات | توكنز | كمون (م/ث) | تكلفة مرجعية |
|---|---|---|---|---|
| 02_invoice_over_limit | 2 | 832 | 12437 | $0.000264 |
| 04_unknown_noise | 1 | 433 | 10624 | $0.000156 |
| 05_letter | 4 | 2054 | 46562 | $0.000693 |

الإجمالي: 3319 توكن، $0.001113
(التكلفة الفعلية 0 — النموذج مجاني؛ الرقم مرجعي بأسعار gpt-4o-mini لإظهار
هندسة التكلفة).

## 4) مجموعة الاختبارات
```
....................................................                     [100%]
52 passed in 2.62s

```
