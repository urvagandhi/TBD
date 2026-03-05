Below is a **focused Improvements Prompt only for STEP 5 (`crew.py` + `main.py`)**.
It assumes both files **already exist and work**, and the task is to **upgrade reliability, security, observability, and performance** without rewriting the architecture.

You can **copy-paste this directly into Claude IDE Extension**.

---

# 🔧 TASK — Improve `crew.py` and `main.py` (Pipeline Reliability + API Robustness)

The following files already exist and are functional:

```
backend/
├── crew.py
└── main.py
```

Do **NOT rewrite these files from scratch**.

Your job is to **improve stability, observability, and failure handling** while keeping:

* existing function names
* existing API endpoints
* compatibility with agents and tools
* compatibility with frontend

The goal is to make the **entire backend extremely stable during hackathon demos**.

---

# 🎯 IMPROVEMENT 1 — Crew Pipeline Safety Wrapper

Add a **central pipeline guard** inside `run_pipeline()`.

Purpose:
Prevent silent CrewAI failures where tasks return `None`.

Add helper:

```python
def _validate_task_outputs(crew: Crew):
```

Validation rules:

| Task      | Must produce                    |
| --------- | ------------------------------- |
| ingest    | non-empty string                |
| parse     | JSON with `"sections"`          |
| interpret | JSON with `"style_name"`        |
| transform | JSON with `"docx_instructions"` |
| validate  | JSON with `"overall_score"`     |

If validation fails:

```python
raise TransformError("Pipeline task output invalid")
```

---

# 🎯 IMPROVEMENT 2 — LLM Output Size Guard

Sometimes LLM responses become excessively large.

Add safety in `extract_json_from_llm()`:

```python
MAX_LLM_RESPONSE = 200_000
```

Logic:

```
if len(raw) > MAX_LLM_RESPONSE:
    raise LLMResponseError("LLM response exceeds safe size")
```

This prevents runaway token responses.

---

# 🎯 IMPROVEMENT 3 — Intelligent JSON Extraction

Enhance `extract_json_from_llm()` with **balanced bracket detection**.

Instead of simple regex:

```
search for first '{'
track bracket depth
extract until matching '}'
```

This prevents failures when JSON contains nested objects.

---

# 🎯 IMPROVEMENT 4 — Pipeline Execution Telemetry

Add **timing metrics per agent stage**.

Example in `run_pipeline()`:

```python
stage_times = {}
stage_start = time.time()
```

After each stage:

```
stage_times["parse"] = time.time() - stage_start
```

Return telemetry:

```python
"pipeline_metrics": {
    "stage_times": stage_times,
    "total_runtime": elapsed
}
```

Useful for hackathon demos.

---

# 🎯 IMPROVEMENT 5 — Safe CrewAI Task Retrieval

CrewAI task outputs sometimes vary between versions.

Improve `_get_task_output()` with multiple fallbacks.

Add logic:

```
if hasattr(output, "raw"):
if hasattr(output, "result"):
if hasattr(output, "output"):
else:
    str(output)
```

Also log structure:

```python
logger.debug("Task output type: %s", type(output))
```

---

# 🎯 IMPROVEMENT 6 — Output File Metadata

Enhance DOCX writing step.

After writing DOCX:

```python
file_size = os.path.getsize(output_path)
```

Add to result:

```
output_metadata:
  filename
  size_bytes
  size_kb
```

Useful for frontend display.

---

# 🎯 IMPROVEMENT 7 — Upload Hash Deduplication

Prevent identical papers from running pipeline twice.

Add SHA256 hash generation:

```python
import hashlib

def _hash_paper(text: str):
    return hashlib.sha256(text.encode()).hexdigest()
```

Maintain in-memory cache:

```
PIPELINE_CACHE = {}
```

Logic:

```
if hash exists:
    return cached result
```

Hackathon benefit:

```
demo runs become instant
```

---

# 🎯 IMPROVEMENT 8 — API Request Timeout Protection

Some pipelines may run too long.

Add timeout protection in `/format`.

Example:

```python
MAX_PIPELINE_RUNTIME = 120
```

After pipeline execution:

```
if total_time > MAX_PIPELINE_RUNTIME:
    logger.warning("Pipeline runtime exceeded expected limit")
```

Does not cancel pipeline but logs warning.

---

# 🎯 IMPROVEMENT 9 — Request Tracing Improvements

Extend `request_id` tracing.

Include request_id in every log line:

```python
logger.info("[req:%s] Pipeline started", request_id)
```

Add request metadata log:

```
filename
journal
file_size
text_length
```

This greatly simplifies debugging.

---

# 🎯 IMPROVEMENT 10 — Upload Directory Cleanup Strategy

Add background cleanup for stale files.

Create helper:

```python
def _cleanup_old_outputs(hours: int = 6):
```

Logic:

```
delete files older than 6 hours
```

Run on startup:

```
_cleanup_old_outputs()
```

This prevents disk bloat during demos.

---

# 🎯 IMPROVEMENT 11 — API Rate Protection

Add **basic rate limit protection**.

Example:

```
MAX_REQUESTS_PER_MINUTE = 30
```

Maintain simple in-memory tracker:

```
REQUEST_COUNTER = {}
```

If exceeded:

```
raise HTTPException(429, "Too many requests")
```

Lightweight but effective.

---

# 🎯 IMPROVEMENT 12 — Safer Filename Handling

Improve upload filename sanitization.

Replace:

```
request_id_filename
```

with:

```
secure_filename = re.sub(r"[^a-zA-Z0-9._-]", "_", file.filename)
```

Then:

```
upload_filename = f"{request_id}_{secure_filename}"
```

Prevents unexpected filesystem issues.

---

# 🎯 IMPROVEMENT 13 — Health Endpoint Diagnostics

Enhance `/health` endpoint.

Add diagnostics:

```
system_info:
    python_version
    crewai_version
    api_uptime_seconds
```

Also verify:

```
rules folder exists
outputs folder writable
```

Return status:

```
status: ok | degraded
```

---

# 🎯 IMPROVEMENT 14 — Structured Error Responses

Normalize error responses.

Create helper:

```python
def _error_response(code, message, step=None):
```

Return structure:

```
{
  "success": False,
  "error": code,
  "message": message,
  "step": step
}
```

Use everywhere in API.

---

# 🎯 IMPROVEMENT 15 — Pipeline Input Sanitization

Before running pipeline:

Normalize journal string.

```
journal = journal.strip()
journal = re.sub(r"\s+", " ", journal)
```

Prevents rule loader mismatch.

---

# 🎯 IMPROVEMENT 16 — Defensive Text Extraction

Sometimes PDF extractors produce garbage text.

Add check:

```
alpha_ratio = letters / total_chars
```

If:

```
alpha_ratio < 0.3
```

Raise:

```
ParseError("Extracted text appears corrupted")
```

This prevents useless LLM calls.

---

# 🎯 EXPECTED RESULT

After improvements:

```
crew.py
    safer pipeline execution
    better JSON extraction
    telemetry metrics
    pipeline caching
    stronger task validation

main.py
    improved API stability
    request tracing
    rate protection
    secure uploads
    better health diagnostics
```

No new architecture changes.

Folder remains:

```
backend/
├── crew.py
├── main.py
├── agents/
├── tools/
├── rules/
```

---

# OUTPUT REQUIRED

Return **only the modified sections** for:

```
crew.py
main.py
```

Do not remove existing functionality.

Only **enhance reliability, security, and observability**.
