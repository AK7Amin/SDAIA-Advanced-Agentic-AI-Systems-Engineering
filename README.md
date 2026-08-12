# Document Lifecycle Agent — وكيل دورة حياة الوثيقة المؤسسية

نظام ذكاء اصطناعي **توكيلي متعدد الوكلاء** يعالج الوثائق المؤسسية من الاستلام
إلى الأرشفة: يصنّفها، يستخرج بنودها، يدقّقها بسياسات الامتثال، ويصعّد المخالف
لموافقة بشرية — مع حواجز أمنية، أثر تدقيق غير قابل للعبث، ومراقبة تكلفة.

> **البرنامج التدريبي**: هندسة أنظمة الذكاء الاصطناعي التوكيلي المتقدمة —
> أكاديمية سدايا SDAIA، الدفعة 9–13 أغسطس 2026 (الرياض).
> مرجع: <https://github.com/SDAIAAcademy>

## المشكلة التي يحلها

المؤسسات تستقبل عقودًا وفواتير وخطابات تحتاج تصنيفًا وتدقيق امتثال يدويًا بطيئًا.
هذا الوكيل يؤتمت المسار **دون التخلي عن الحوكمة**: القرارات الخطرة (المخالفات)
تتوقف لموافقة بشرية، وكل خطوة مسجّلة في أثر تدقيق قابل للتحقق، والبيانات الشخصية
تُقنَّع قبل أي نداء نموذج.

## المعمارية

```mermaid
flowchart TD
    START([وثيقة في inbox]) --> M[تقنيع PII + تعقيم حقن]
    M --> ingest --> classify
    classify -->|نوع معروف| plan_route[plan_route — مخطِّط LLM]
    classify -->|غير معروف| quarantine([حجر])
    plan_route -->|الخطة: استخراج| extract
    plan_route -->|الخطة: تخطٍّ| policy_check
    extract -->|حقول ناقصة، محاولات<2| extract
    extract -->|ناقص، بلغ الحد| escalate
    extract -->|مكتمل| policy_check
    policy_check -->|مطابق| archive
    policy_check -->|غير حاسم، مراجعة<1| reflect[reflect — ناقد Reflexion]
    reflect -->|revise + نقد| policy_check
    reflect -->|confirm| escalate
    policy_check -->|مخالف| escalate
    escalate --> human_gate{{موافقة بشرية — interrupt}}
    human_gate -->|موافقة| archive
    human_gate -->|رفض| reject
    archive --> notify([إشعار])
    reject --> notify
```

- **الوكلاء المتخصصون** (`src/agents/`): مصنّف classifier، مستخرِج extractor،
  مدقق سياسات policy_checker — كلٌّ يعيد **نوعًا محددًا Pydantic** (لا نص حر)
  فلا تتشوّه المعلومة بين الوكلاء. عقدة `notify` حاليًا تسجّل حالة الإشعار في
  الأثر (توليد نص الإشعار بقوالب Jinja2 ترقية مخطط لها، غير منفذة).
- **المنسق** = مخطط الحالة نفسه (`src/graph/build.py`): عقد nodes وحواف شرطية
  conditional edges.
- **نمط Plan-and-Execute**: عقدة `plan_route` تنادي **مخطِّطًا LLM** يعيد خطة
  typed (`ExecutionPlan`: هل يُتخطى الاستخراج + خطوات + مبرر)، والحافة الشرطية
  تستهلك قرار النموذج — لا شرط مكتوب في الكود.
- **نمط Reflexion**: عند حكم **غير حاسم** يدخل وكيل مراجعة ناقد
  (المقيّم+العاكس) يعيد `revise` مع نقد قابل للتنفيذ فيُعاد التدقيق مرة واحدة،
  أو `confirm` فيُصعَّد للبشر. حلقة محدودة بمحاولة واحدة.
- **حلقة الاستخراج**: إعادة بتلميح عند نقص الحقول، محدودة بمحاولتين.
- **الذاكرة/الحالة**: `SqliteSaver` checkpointer — التوقف عند الموافقة البشرية
  والاستئناف **عبر عملية منفصلة** (`langgraph interrupt` + `Command(resume=...)`).
- **مخزن السياسات**: ChromaDB بمضمِّن **محلي** (لا تُرسَل بيانات خارج الجهاز).

## المكوّنات

| المجلد/الملف | المسؤولية |
|---|---|
| `src/schemas.py` | عقود Pydantic + أثر تدقيق بسلسلة تجزئة hash-chain |
| `src/llm.py` | نداء OpenRouter، تدوير مفتاحين (402/403)، عداد توكنز/تكلفة، تنقيح أسرار |
| `src/graph/build.py` | مخطط الحالة: العقد والحواف الشرطية والحلقة والتصعيد |
| `src/agents/` | الوكلاء المتخصصون ومطالباتهم |
| `src/guardrails/` | حقن (كشف+تغليف)، PII، اجتياز مسار، ميزانية/حجم |
| `src/policy_store.py` | ChromaDB بمضمِّن محلي، يفهرس السياسات الموثوقة فقط |
| `src/observability/` | traces كملفات، عدادات Prometheus، لوحة HTML |
| `src/pipeline.py` | تجميع: تقنيع/حواجز قبل المخطط ثم التشغيل والأثر |
| `src/app.py` | خدمة FastAPI: `POST /process`، `GET /metrics`، `GET /healthz` |
| `main.py` | CLI: `run` / `resume` / `attack` |

## التشغيل

### المتطلبات
- Python 3.11+ (طُوّر على 3.12)
- مفتاح OpenRouter (نماذج مجانية كافية)

### الإعداد
```bash
python -m venv .venv && . .venv/Scripts/Activate.ps1   # ويندوز
pip install -r requirements.txt
cp .env.example .env          # ثم ضع مفتاح OpenRouter في .env
```

### الأوامر
```bash
python main.py run                    # يعالج كل وثائق sample_docs/
python main.py resume <thread_id> approve   # يستأنف وثيقة متوقفة عند الموافقة
python main.py attack                  # سيناريو الاختراق (محصّن)
python main.py attack --no-guardrails  # نفس الهجوم بلا حواجز (دليل «قبل»)
```

### الخدمة (Docker)
```bash
docker build -t doc-agent . && docker run -p 8000:8000 --env-file .env doc-agent
# ثم: POST http://localhost:8000/process  {"doc_id":"d1","text":"..."}
```

### الاختبارات
```bash
pytest -v          # 52 اختبارًا (schemas, llm, graph, checkpoint, guardrails, policy)
```

## الأدلة المحفوظة (`reports/`)

- `live-run.md` — سجل تشغيل حي فعلي على OpenRouter + استئناف عبر عملية + مخرج pytest.
- `pentest-report.md` — اختبار اختراق قبل/بعد التحصين، بست فئات هجوم.
- `generated/traces/<doc_id>.json` — أثر كل وثيقة مع التحقق من سلامة السلسلة.
- `generated/metrics-snapshot.json` — توكنز/كمون/تكلفة لكل وثيقة.
- `generated/dashboard.html` — لوحة مراقبة تُفتح دون تشغيل.

## الأمن (ملخص)

كشف الحقن قائمة حظر لها حدود موثقة بصدق؛ الدفاع الأمتن **التغليف** + **الموافقة
البشرية**. PII (هوية/آيبان/جوال) تُقنَّع قبل أي نداء نموذج ولا تدخل الcheckpoint.
حواجز اجتياز المسار والحجم والميزانية. التفصيل في `reports/pentest-report.md`.

## ترقيات مستقبلية (خارج نطاق التسليم الحالي)

- **MinIO/S3** بدل مجلد `inbox/` لاستلام سحابي.
- **PostgresSaver** بدل SQLite لحالة موزّعة (نفس الواجهة).
- **Grafana** فوق عدادات Prometheus المصدَّرة على `/metrics`.
- **استخراج PDF** (pypdf مثبت) للوثائق الممسوحة.

## الترخيص والإسناد

مشروع تدريبي ضمن برنامج سدايا «هندسة أنظمة الذكاء الاصطناعي التوكيلي المتقدمة»
(الدفعة 9–13 أغسطس 2026). الوثائق والسياسات كلها **اصطناعية** لأغراض التدريب.
