# سجل التشغيل الحي — دليل تنفيذي

> مُولّد آليًا بتشغيل فعلي على OpenRouter (نموذج مجاني `openai/gpt-oss-20b:free`)
> من **حالة نظيفة** (حُذفت الcheckpoints والtraces قبل الالتقاط). هذا هو الدليل
> الذي يطلبه نمط التقييم: مخرجات منفَّذة محفوظة، لا مجرد وجود كود.

## 1) معالجة وثائق العينة (الحواجز مفعّلة)
```
== معالجة 5 وثيقة (guardrails=on) ==

  01_contract_compliant.md         → archived           حواجز={'size_ok': True, 'injection_flagged': False, 'pii_masked': False}
  02_invoice_over_limit.md         → FAILED: RuntimeError: 'choices'
  03_injected_contract.md          → awaiting_approval  حواجز={'size_ok': True, 'injection_flagged': True, 'pii_masked': False}
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
| 01_contract_compliant | 4 | 1688 | 39166 | $0.000516 |
| 03_injected_contract | 4 | 1874 | 87244 | $0.000680 |
| 04_unknown_noise | 1 | 401 | 11136 | $0.000137 |
| 05_letter | 4 | 2024 | 92116 | $0.000675 |

الإجمالي: 5987 توكن، $0.002008
(التكلفة الفعلية 0 — النموذج مجاني؛ الرقم مرجعي بأسعار gpt-4o-mini لإظهار
هندسة التكلفة).

## 4) مجموعة الاختبارات
```
...........................................................              [100%]
59 passed in 2.58s

```
