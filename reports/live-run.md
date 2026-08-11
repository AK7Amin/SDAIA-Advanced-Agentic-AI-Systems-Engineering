# سجل التشغيل الحي — دليل تنفيذي

> مُولّد آليًا بتشغيل فعلي على OpenRouter (نموذج مجاني `openai/gpt-oss-20b:free`)
> من **حالة نظيفة** (حُذفت الcheckpoints والtraces قبل الالتقاط). هذا هو الدليل
> الذي يطلبه نمط التقييم: مخرجات منفَّذة محفوظة، لا مجرد وجود كود.

## 1) معالجة وثائق العينة (الحواجز مفعّلة)
```
== معالجة 5 وثيقة (guardrails=on) ==

  01_contract_compliant.md         → archived           حواجز={'size_ok': True, 'injection_flagged': False, 'pii_masked': False}
  02_invoice_over_limit.md         → awaiting_approval  حواجز={'size_ok': True, 'injection_flagged': False, 'pii_masked': False}
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
استُؤنف 02_invoice_over_limit بقرار «approve» → archived

```
الفاتورة توقفت عند الموافقة البشرية في العملية الأولى، ثم استُؤنفت في **عملية بايثون منفصلة** فأكملت إلى الأرشفة — دليل استمرارية الحالة عبر حدود العملية.

## 3) التكلفة والكمون لكل وثيقة (من metrics-snapshot.json)
| الوثيقة | نداءات | توكنز | كمون (م/ث) | تكلفة مرجعية |
|---|---|---|---|---|
| 01_contract_compliant | 3 | 1262 | 17905 | $0.000384 |
| 02_invoice_over_limit | 3 | 1115 | 17633 | $0.000327 |
| 03_injected_contract | 3 | 1443 | 37363 | $0.000531 |
| 04_unknown_noise | 1 | 433 | 10210 | $0.000156 |
| 05_letter | 2 | 876 | 24356 | $0.000283 |

الإجمالي: 5129 توكن، $0.001682
(التكلفة الفعلية 0 — النموذج مجاني؛ الرقم مرجعي بأسعار gpt-4o-mini لإظهار
هندسة التكلفة).

## 4) مجموعة الاختبارات
```
.................................................                        [100%]
49 passed in 2.58s

```
