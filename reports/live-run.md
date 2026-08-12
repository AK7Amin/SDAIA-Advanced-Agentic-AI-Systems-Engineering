# سجل التشغيل الحي — دليل تنفيذي

> مُولّد آليًا بتشغيل فعلي على OpenRouter (نموذج مجاني `openai/gpt-oss-20b:free`)
> من **حالة نظيفة** (حُذفت الcheckpoints والtraces قبل الالتقاط). هذا هو الدليل
> الذي يطلبه نمط التقييم: مخرجات منفَّذة محفوظة، لا مجرد وجود كود.

## 1) معالجة وثائق العينة (الحواجز مفعّلة)
```
== معالجة 7 وثيقة (guardrails=on) ==

  01_contract_compliant.md         → archived           حواجز={'size_ok': True, 'injection_flagged': False, 'pii_masked': False}
  02_invoice_over_limit.md         → awaiting_approval  حواجز={'size_ok': True, 'injection_flagged': False, 'pii_masked': False}
  03_injected_contract.md          → awaiting_approval  حواجز={'size_ok': True, 'injection_flagged': True, 'pii_masked': False}
  04_unknown_noise.txt             → quarantined        حواجز={'size_ok': True, 'injection_flagged': False, 'pii_masked': False}
  05_letter.md                     → awaiting_approval  حواجز={'size_ok': True, 'injection_flagged': False, 'pii_masked': False}
  06_contract_pdf_compliant.pdf    → archived           حواجز={'size_ok': True, 'injection_flagged': False, 'pii_masked': False}
  07_contract_pdf_over_limit.pdf   → awaiting_approval  حواجز={'size_ok': True, 'injection_flagged': False, 'pii_masked': False}

لقطة المقاييس: C:\Users\abdul\Desktop\Islamic Content Association\SDAIA Advanced Agentic AI Systems Engineering\capstone-doc-lifecycle\reports\generated\metrics-snapshot.json

```
**القراءة**: عقد مطابق → أُرشف آليًا | فاتورة تتجاوز حد السياسة → توقفت لموافقة
بشرية | وثيقة تحمل حقنًا → عُلِّم الحقن وصُعّدت | ضجيج → حُجر | خطاب → تخطّى
الاستخراج عبر plan_route.

## 2) الاستئناف الحي عبر عملية جديدة (بند الذاكرة/الحالة)
```
استُؤنف 02_invoice_over_limit بقرار «approve» → archived

```
الفاتورة توقفت عند الموافقة البشرية في العملية الأولى، ثم استُؤنفت في **عملية بايثون منفصلة** فأكملت إلى الأرشفة — دليل استمرارية الحالة عبر حدود العملية.

## 3) التكلفة والكمون لكل وثيقة (من metrics-snapshot.json)
| الوثيقة | نداءات | توكنز | كمون (م/ث) | تكلفة مرجعية |
|---|---|---|---|---|
| 01_contract_compliant | 5 | 2807 | 72431 | $0.001051 |
| 02_invoice_over_limit | 4 | 1668 | 46342 | $0.000539 |
| 03_injected_contract | 5 | 3103 | 96864 | $0.001211 |
| 04_unknown_noise | 1 | 401 | 9110 | $0.000137 |
| 05_letter | 4 | 2424 | 52950 | $0.000915 |
| 06_contract_pdf_compliant | 5 | 2823 | 59840 | $0.001070 |
| 07_contract_pdf_over_limit | 5 | 2785 | 55733 | $0.001055 |

الإجمالي: 16011 توكن، $0.005977
(التكلفة الفعلية 0 — النموذج مجاني؛ الرقم مرجعي بأسعار gpt-4o-mini لإظهار
هندسة التكلفة).

## 4) مجموعة الاختبارات
```
........................................................................ [ 91%]
.......                                                                  [100%]
79 passed in 9.50s

```
