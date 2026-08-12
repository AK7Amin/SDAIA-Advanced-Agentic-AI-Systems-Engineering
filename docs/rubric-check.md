# جدول التحقق مقابل الرُبرِك الرسمي

مصدر البنود: `Capstone Rubric - Advanced Agentic AI Systems Engineering.pdf`
(100 نقطة، النجاح 60، ولا بند يقل عن **40%** من نقاطه).

كل صف يحيل إلى **دليل تنفيذ** (كود) و**دليل تشغيل** (مخرج محفوظ من تشغيلة حية).

---

## البند 1 — الاستدلال التوكيلي واستخدام الأدوات (15)

| المطلوب | أين يتحقق | دليل التشغيل |
|---|---|---|
| أدوات/دوال حقيقية لا مخرجات مبرمجة | `src/tools.py`: `policy_lookup` يبحث في ChromaDB، `calculator` بمحلّل AST | `reports/live-run.md` §2 — نتائج فعلية داخل الأثر |
| **واجهة بنمط MCP** | `ToolCall(name, arguments)` + `inputSchema` لكل أداة + `list_tools()` (نفس حقول `tools/list`) + موزِّع `dispatch` يتحقق قبل التنفيذ + `execution_log` | `tests/test_tool_interface.py` (14 اختبارًا) |
| نمط استدلال مُسمّى من الدورة | **ثلاثة** منفّذة: ReAct (`src/agents/react.py`)، Plan-and-Execute (`plan_route`)، Reflexion (`reflect`) | أثر 01: `uncertain → reflect → compliant` |
| ذاكرة قصيرة المدى | دفتر scratchpad يُمرَّر كاملًا في كل خطوة | `tests/test_tools_react.py::test_scratchpad_carries_short_term_memory` |
| صدق الإسناد | `decision_source`: `model` \| `policy_enforced` \| `fallback_direct_retrieval` | وسم `[مصدر=…]` على كل حدث أداة في كل أثر |

## البند 2 — التنسيق بمخطط حالة (20)

| المطلوب | أين يتحقق | دليل التشغيل |
|---|---|---|
| مخطط حالة حقيقي | LangGraph `StateGraph`، 12 عقدة (`src/graph/build.py`) | مخطط mermaid في README |
| حافة شرطية واحدة على الأقل | **ست** حواف شرطية: `after_classify`, `after_plan`, `after_extract`, `after_policy`, `after_reflect`, `after_human` | `tests/test_graph_paths.py` |
| حالة مشتركة حقيقية تقرأ وتُكتب | `DocState` TypedDict + reducer تراكمي لأثر التدقيق | `tests/test_graph_paths.py::test_audit_trail_appends_never_replaces` |
| حلقة تنتهي بشرط | حلقتان محدودتان: الاستخراج (محاولتان)، Reflexion (مراجعة واحدة) | `test_extraction_loop_bounded_then_escalates` + أثر 01 حيًا |
| ليست سلسلة خطية مقنّعة | قرار **النموذج** (خطة typed) يوجّه التدفق لا شرط مكتوب | `test_planner_decision_drives_control_flow` |

## البند 3 — تعدد الوكلاء وتخصص الأدوار (20)

| المطلوب | أين يتحقق | دليل التشغيل |
|---|---|---|
| وكيلان فأكثر بأدوار مسماة | خمسة: مصنّف، مخطِّط، مستخرِج، مدقق سياسات، مراجع ناقد (`src/agents/real.py`) | كل أثر يُظهر عقدة كل وكيل بقراره |
| تواصل برسائل منظّمة | عقود Pydantic بين الوكلاء: `Classification`, `ExecutionPlan`, `ExtractedFields`, `PolicyVerdict`, `ReviewVerdict` — لا نص حر | `tests/test_schemas.py` |
| استراتيجية تنسيق معلنة | **مركزية**: المخطط نفسه هو المنسق، والتفويض عبر الحالة المشتركة لا عبر نداء وكيل لوكيل | README §المعمارية |

## البند 4 — الأمن والحواجز والمراقبة (20)

| المطلوب | أين يتحقق | دليل التشغيل |
|---|---|---|
| حاجز مدخلات + هجوم حقيقي يُحجب | كشف الحقن (قائمة حظر + تطبيع Unicode/كشيدة) + تغليف البيانات غير الموثوقة | `live-run.md` §3 ومقارنة قبل/بعد، و`reports/pentest-report.md` |
| حاجز مخرجات/حماية بيانات | تقنيع PII (هوية/آيبان/جوال) **قبل** أي نداء نموذج وقبل الcheckpoint | `tests/test_pipeline_masking.py` |
| مراقبة منظمة (لا print) | عدادات Prometheus + `/metrics` + آثار JSON + لقطة مقاييس + لوحة HTML | `generated/metrics-snapshot.json`, `dashboard.html`, `traces/` |
| تلتقط استدعاءات الأدوات والكمون والتكلفة والفشل | كل استدعاء أداة حدثٌ في الأثر؛ التوكنز/الكمون/التكلفة لكل عقدة ولكل وثيقة | `live-run.md` §7 |
| زيادة على المطلوب | أثر تدقيق بسلسلة تجزئة + فاحص مستقل، وحاجز ميزانية، وحاجز اجتياز مسار، وتقييد فك تسلسل الcheckpoint بقائمة سماح | `live-run.md` §6، `tests/test_checkpoint_serde.py` |

## البند 5 — جاهزية الإنتاج: الاستمرارية والموافقة البشرية والسحابة (20)

| المطلوب | أين يتحقق | دليل التشغيل |
|---|---|---|
| checkpointer دائم ينجو من إعادة التشغيل | `SqliteSaver` على القرص (`src/checkpointing.py`) | `live-run.md` §4 — استئناف من عملية جديدة |
| عقدة موافقة بشرية توقف وتستأنف | `escalate` ثم `human_gate` بـ`interrupt()`، والاستئناف بـ`Command(resume=…)` | الفرعان: approve → archived، reject → rejected |
| أثر نشر سحابي | `Dockerfile` + `.dockerignore` + خدمة FastAPI (`/process`, `/resume`, `/metrics`, `/healthz`) | `src/app.py`, `tests/` |
| مسار فشل/تراجع فعلي | إعادة محاولة بتراجع أسّي ثم تدوير مفتاح | `live-run.md` §5 |

## البند 6 — التوثيق ودليل التنفيذ (5)

| المطلوب | أين يتحقق |
|---|---|
| مخرجات حقيقية محفوظة لكل بند | `reports/generated/logs/` (7 سجلات) + `traces/` (9 آثار) + `metrics-snapshot.json` |
| كتابة معمارية بمفردات الدورة | README: عقد nodes، حواف edges، حالة state، وكلاء agents، أدوات tools |
| ممارسات git | تاريخ تدريجي برسائل ذات معنى، `.gitignore` يستبعد الأسرار والمولَّدات |
| إسناد البرنامج | README يذكر البرنامج والدفعة ويحيل إلى <https://github.com/SDAIAAcademy> |

---

## ما لم يُنفَّذ (معلن بصدق)

- **MinIO/S3** و**PostgresSaver** و**Grafana**: مذكورة كترقيات في README، لا
  كادعاءات منفَّذة. الرُبرِك يقبل Dockerfile أو خدمة FastAPI بديلًا، وكلاهما قائم.
- **OCR** للوثائق الممسوحة ضوئيًا: خارج النطاق (استخراج PDF النصي منفَّذ).
- **الوكلاء ككائنات مستقلة**: منفَّذون كدوال متخصصة على `RealAgents` تُحقن في
  المخطط. الرُبرِك يشترط أدوارًا مسماة تتواصل برسائل منظّمة — وهو محقق — لا شكلًا
  كائنيًا بعينه.
