# Document Lifecycle Agent — وكيل دورة حياة الوثيقة المؤسسية

نظام ذكاء اصطناعي **توكيلي متعدد الوكلاء** يعالج الوثائق المؤسسية من الاستلام
إلى الأرشفة: يصنّفها، يستخرج بنودها، يدقّقها بسياسات الامتثال، ويصعّد المخالف
لموافقة بشرية — مع حواجز أمنية، أثر تدقيق غير قابل للعبث، ومراقبة تكلفة.

> **البرنامج التدريبي**: هندسة أنظمة الذكاء الاصطناعي التوكيلي المتقدمة —
> أكاديمية سدايا SDAIA، الدفعة 9–13 أغسطس 2026 (الرياض).
> مرجع: <https://github.com/SDAIAAcademy>

## للمصحّح — أين دليل كل بند

كل بند في الرُبرِك له **كود** و**دليل تشغيل حي محفوظ** (مخرج فعلي، لا كود
«يمكن أن يعمل»). الروابط قابلة للنقر:

| البند | الكود | الدليل الحي |
|---|---|---|
| 1 — الاستدلال واستخدام الأدوات (15) | [src/tools.py](src/tools.py) · [src/agents/react.py](src/agents/react.py) | [live-run.md](reports/live-run.md) §2 — استدعاءات أدوات حقيقية بوسائطها ونتائجها |
| 2 — التنسيق بمخطط حالة (20) | [src/graph/build.py](src/graph/build.py) | [traces/](reports/generated/traces/) — حواف شرطية وحلقتان محدودتان في الأثر |
| 3 — تعدد الوكلاء والأدوار (20) | [src/agents/real.py](src/agents/real.py) · [src/schemas.py](src/schemas.py) | كل أثر يُظهر قرار كل وكيل كعقد Pydantic منفصل |
| 4 — الأمن والحواجز والمراقبة (20) | [src/guardrails/](src/guardrails/) · [src/observability/](src/observability/) | [pentest-report.md](reports/pentest-report.md) · [metrics-snapshot.json](reports/generated/metrics-snapshot.json) |
| 5 — جاهزية الإنتاج (20) | [Dockerfile](Dockerfile) · [src/app.py](src/app.py) · [src/checkpointing.py](src/checkpointing.py) | [09-docker-run.log](reports/generated/logs/09-docker-run.log) — حاوية تعمل فعلًا · [04-hitl-resume.log](reports/generated/logs/04-hitl-resume.log) — استئناف عبر عملية |
| 6 — التوثيق ودليل التنفيذ (5) | هذا الملف | [generated/logs/](reports/generated/logs/) — تسعة سجلات خام |

**الجدول الكامل بند-بند مع كل مسار دليل**: **[docs/rubric-check.md](docs/rubric-check.md)**

للتحقق بنفسك في دقيقة واحدة، بلا مفتاح ولا شبكة:

```bash
pytest -q                      # 136 اختبارًا
python main.py verify-traces   # يعيد حساب سلسلة تجزئة كل أثر ولا يثق بالمكتوب
```

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
  فلا تتشوّه المعلومة بين الوكلاء.
- **أفعال حقيقية لا حالات**: `archive` يكتب الوثيقة **ويقيّد القرار** في قاعدة
  SQLite قابلة للاستعلام، و`notify` يولّد نص الإشعار بقالب Jinja2 ويكتبه ملفًا.
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
- **استيعاب PDF حقيقي**: عقود PDF عربية تُقرأ بـ`pypdf` وتُطبَّع (صيغ العرض
  presentation forms ← حروف عادية، أرقام عربية-هندية ← لاتينية، تواريخ مقلوبة
  ← ISO). القاعدة المتبعة من خبرة سابقة: **لا** إعادة تشكيل reshaping قبل
  النموذج — تعكس النص منطقيًا وتدمّر فهمه.

## المكوّنات

| المجلد/الملف | المسؤولية |
|---|---|
| `src/schemas.py` | عقود Pydantic + أثر تدقيق بسلسلة تجزئة hash-chain |
| `src/llm.py` | سلسلة مزودين متوافقين مع واجهة OpenAI، تدوير على 401/402/403/429، عداد توكنز/كمون/تكلفة، تنقيح أسرار |
| `src/graph/build.py` | مخطط الحالة: العقد والحواف الشرطية والحلقة والتصعيد |
| `src/agents/` | الوكلاء المتخصصون ومطالباتهم |
| `src/tools.py` | **واجهة أدوات بنمط MCP**: مخطط مدخلات معلن لكل أداة، `ToolCall` متحقق منه، موزِّع واحد، وسجل تنفيذ |
| `src/checkpointing.py` | باني الcheckpointer بمُسلسِل **مقيَّد بقائمة سماح** لأنواع المشروع |
| `src/agents/react.py` | حلقة ReAct: فكرة ← فعل ← ملاحظة، بذاكرة قصيرة المدى |
| `src/guardrails/` | حقن (كشف+تغليف)، PII، اجتياز مسار، ميزانية/حجم |
| `src/policy_store.py` | ChromaDB بمضمِّن محلي، يفهرس السياسات الموثوقة فقط |
| `src/observability/` | traces كملفات، عدادات Prometheus، لوحة HTML |
| `src/loaders.py` | استخراج نص من **PDF حقيقي** (pypdf) + تطبيع تشوهات العربية |
| `tools/make_sample_pdfs.py` | أداة تطوير: توليد عقود PDF عربية اصطناعية |
| `src/effects.py` | الأفعال الحقيقية: أرشفة الوثيقة + قيد القرار في SQLite + إشعار Jinja2 |
| `src/pipeline.py` | تجميع: تقنيع/حواجز قبل المخطط ثم التشغيل والأثر |
| `src/app.py` | خدمة FastAPI: `POST /process`، `POST /resume`، `GET /metrics`، `GET /healthz` |
| `main.py` | CLI: `run` / `resume` / `attack` / `resilience-demo` |

## التشغيل

### المتطلبات
- Python 3.11+ (طُوّر على 3.12)
- مفتاح أي مزوّد يتكلم واجهة OpenAI المتوافقة (OpenRouter بنماذجه المجانية،
  أو Mistral، أو غيرهما) — المزوّد يُبدَّل بمتغيري بيئة بلا لمس كود.

### الإعداد
```bash
python -m venv .venv && . .venv/Scripts/Activate.ps1   # ويندوز
pip install -r requirements.txt
cp .env.example .env          # ثم ضع المفتاح في .env
```

**متغيرات البيئة** (كلها في `.env.example`):

| المتغير | معناه |
|---|---|
| `LLM_API_KEY` | مفتاح المزوّد (تُقبل `OPENROUTER_API_KEY` للتوافق الخلفي) |
| `LLM_API_KEY_FALLBACK` | مفتاح احتياطي يُدوَّر إليه عند 402/403/429 |
| `LLM_BASE_URL` | نقطة النهاية (الافتراضي OpenRouter) |
| `LLM_MODEL` | اسم النموذج |
| `MAX_LLM_CALLS_PER_DOC` | حاجز الميزانية لكل وثيقة (افتراضي 12) |
| `LLM_BASE_URL_2` / `LLM_MODEL_2` / `LLM_API_KEY_2` | مزوّد ثانٍ يتولّى تلقائيًا عند نفاد الحصة |
| `API_TOKEN` | اعتماد `POST /process`؛ بدونه تُغلق نقطة النهاية (503) |
| `APPROVAL_API_TOKEN` | اعتماد `POST /resume`؛ بدونه تُغلق البوابة (503) |

### الأوامر
```bash
python main.py run                     # يعالج كل وثائق sample_docs/
python main.py resume <thread_id> approve   # يستأنف وثيقة متوقفة عند الموافقة
python main.py attack                  # سيناريو الاختراق (محصّن)
python main.py attack --no-guardrails  # نفس الهجوم بلا حواجز (دليل «قبل»)
python main.py resilience-demo         # إعادة محاولة ← تدوير مفتاح ← نجاح
python main.py verify-traces           # فحص مستقل لسلامة كل أثر محفوظ
```

`run` يطبع لكل وثيقة متوقفة **معرّف خيطها** لتستأنفه بـ`resume`. وكل تشغيلة —
في واجهة الأوامر وفي الخدمة معًا — تأخذ معرّف خيط فريدًا، فلا تستأنف تشغيلةً
سابقة ولا يندمج أثران في ملف واحد. و`verify-traces` يكشف الاندماج لو وقع.

### الخدمة (Docker)
```bash
docker build -t doc-agent . && docker run -p 8000:8000 --env-file .env doc-agent
# ثم: POST http://localhost:8000/process  {"doc_id":"d1","text":"..."}
```

المسارات: `POST /process`، و`POST /resume` (يتطلب ترويسة `X-Approval-Token`
مطابقة لـ`APPROVAL_API_TOKEN`، وبدونها تُغلق البوابة بـ503)، و`GET /metrics`،
و`GET /healthz`. دليل تشغيل فعلي (بناء + نداءات على الحاوية) في
`reports/generated/logs/08-docker-build.log` و`09-docker-run.log`.

### الاختبارات
```bash
pytest -q          # 136 اختبارًا (عقود، نموذج، مخطط، checkpoint، حواجز، أدوات، وصل)
```

## الأدلة المحفوظة (`reports/`)

- [`reports/live-run.md`](reports/live-run.md) — **دليل التشغيل المركزي**: التقاط واحد نظيف لكل ما يطلبه
  الرُبرِك (ثماني وثائق، هجوم قبل/بعد، إيقاف واستئناف عبر عملية، مرونة، مقاييس).
- [`reports/generated/logs/`](reports/generated/logs/) — المخرجات **الخام** لكل أمر كما طُبعت (تسعة سجلات،
  منها بناء صورة Docker وتشغيل الحاوية ونداءات HTTP عليها).
- [`docs/rubric-check.md`](docs/rubric-check.md) — جدول تحقق: كل بند في الرُبرِك ← مسار دليله.
- [`reports/pentest-report.md`](reports/pentest-report.md) — اختبار اختراق قبل/بعد التحصين، بست فئات هجوم.
- [`reports/generated/traces/`](reports/generated/traces/) — أثر كل وثيقة مع التحقق من سلامة السلسلة.
- [`reports/generated/metrics-snapshot.json`](reports/generated/metrics-snapshot.json) — توكنز/كمون/تكلفة لكل وثيقة.
- [`reports/generated/dashboard.html`](reports/generated/dashboard.html) — لوحة مراقبة تُفتح دون تشغيل.
- [`archive/`](archive/) + [`reports/notifications/`](reports/notifications/) — **مخرجات أفعال حقيقية**: الوثائق
  المؤرشفة والإشعارات المولَّدة. وقاعدة `archive/decisions.sqlite` تحمل قيد كل
  قرار (قابلة للاستعلام) **كسجل تاريخي تراكمي** — قيد مستقل لكل قرار حتى لو
  تكرر معرّف الوثيقة. لا تُتتبَّع في git لأنها ثنائية وتُعاد توليدها بالتشغيل.

## الأمن (ملخص)

كشف الحقن قائمة حظر لها حدود موثقة بصدق؛ الدفاع الأمتن **التغليف** + **الموافقة
البشرية**. PII (هوية/آيبان/جوال) تُقنَّع قبل أي نداء نموذج ولا تدخل الcheckpoint.
حواجز اجتياز المسار والحجم والميزانية. التفصيل في `reports/pentest-report.md`.

## ترقيات مستقبلية (خارج نطاق التسليم الحالي)

- **MinIO/S3** بدل مجلد `inbox/` لاستلام سحابي.
- **PostgresSaver** بدل SQLite لحالة موزّعة (نفس الواجهة).
- **Grafana** فوق عدادات Prometheus المصدَّرة على `/metrics`.
- **OCR** للوثائق **الممسوحة ضوئيًا** (استخراج PDF النصي منفَّذ بالفعل).

## الترخيص والإسناد

مشروع تدريبي ضمن برنامج سدايا «هندسة أنظمة الذكاء الاصطناعي التوكيلي المتقدمة»
(الدفعة 9–13 أغسطس 2026). الوثائق والسياسات كلها **اصطناعية** لأغراض التدريب.
