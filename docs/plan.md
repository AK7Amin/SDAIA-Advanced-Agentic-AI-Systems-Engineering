# خطة البناء — وكيل دورة حياة الوثيقة المؤسسية
# Document Lifecycle Agent — Build Plan

> النسخة 1 (قبل نقد الوكلاء الثلاثة). كل بند مربوط ببند rubric متوقع
> (انظر rubric-predicted.md). المنهج: TDD صارم — الاختبار قبل التنفيذ.

## 0) الفكرة في سطرين

وثائق عربية اصطناعية تصل `inbox/` ← وكيل مصنّف يحدد النوع ← وكيل مستخرج يخرج
البنود بعقد Pydantic ← وكيل مدقق يقارنها بسياسات في ChromaDB ← حافة شرطية:
مطابقة تُؤرشف، مخالفة تتجمد عند موافقة بشرية (interrupt + checkpoint يُستأنف
عبر عملية جديدة) ← إشعار Jinja2 عربي. وطوال المسار: حواجز، أثر تدقيق مسلسل
التجزئة hash-chained، وقياسات.

## 1) المعمارية

### الحالة المشتركة (TypedDict + Pydantic)
```
DocState: doc_id, file_path, raw_text, masked_text,
          doc_type + confidence, extraction: ExtractionResult,
          findings: list[PolicyFinding], decision: Decision,
          human_verdict, retry_count, audit: list[AuditEntry],
          usage: TokenUsage, error
```

### عقد المخطط (LangGraph StateGraph + SqliteSaver)
```
intake → classify → plan_route → extract → policy_check → route_decision
route_decision (حافة شرطية):
  - compliant            → archive → notify → END
  - violation/uncertain  → human_approval (interrupt) → [resume] → archive/reject → notify → END
  - low_confidence extraction (retry_count < 2) → extract   ← الحلقة
  - low_confidence (retry_count == 2)           → human_approval
```
- `plan_route`: عقدة تخطيط — النموذج يقرر مخطط الاستخراج وحزمة السياسات
  حسب نوع الوثيقة (Plan-and-Execute مصغّر: القرار للنموذج لا للكود).
- كل عقدة = وكيل متخصص له system prompt خاص ومخرج Pydantic ملزم.
- المنسق = المخطط نفسه + عقدة route_decision (قرار مركزي، تقارير مباشرة).

### طبقة النموذج `src/llm.py`
- OpenRouter عبر openai SDK بـbase_url، الموديل من `.env` (المجاني افتراضيًا).
- تدوير مفتاحين عند 402 **و403** (درس ذاكرة الجمعية المثبت).
- عداد توكنز/تكلفة لكل نداء يغذي المراقبة.
- `FakeLLM` حتمي للاختبارات: يُعطى سيناريو ردود مسبقة.

### الحواجز `src/guardrails/`
1. **مدخلات**: أنماط حقن (عربي+إنجليزي)، كشف PII (هوية/آيبان/جوال) ←
   تقنيع mask قبل أي نداء نموذج (يوافق قاعدة R021).
2. **تعقيم استرجاع**: نص الوثيقة والسياسات يُغلفان كبيانات بين محددات +
   تعليمة تصلب — أي أمر داخل وثيقة يُتجاهل ويُعلَّم كمحاولة حقن.
3. **مخرجات**: التحقق Pydantic + إعادة محاولة عند مخرج فاسد (حد 2).
4. **ميزانية**: حد نداءات نموذج لكل وثيقة (يمنع انفجار التكلفة).

### المراقبة `src/observability/`
- أثر trace بJSONL لكل تشغيلة (عقد