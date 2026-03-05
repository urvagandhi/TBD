Below is a **focused Improvements Prompt only for STEP 4 (Agents Layer)**.
It assumes the **5 agents are already implemented** and asks Claude to **upgrade them for reliability, performance, determinism, and hackathon-grade robustness** without rewriting everything.

You can **copy-paste this directly into Claude IDE Extension**.

---

# 🔧 TASK — Improve CrewAI Agents Layer (Reliability + Determinism + Robustness)

The following agents already exist:

```
backend/agents/
├── ingest_agent.py
├── parse_agent.py
├── interpret_agent.py
├── transform_agent.py
└── validate_agent.py
```

Do **NOT rewrite these agents from scratch**.

Your task is to **improve the current implementation** while keeping:

* existing file names
* existing function names
* existing agent/task exports
* compatibility with `crew.py`

The goal is to make the **pipeline extremely stable during hackathon demos**.

---

# 🎯 IMPROVEMENT 1 — Deterministic LLM Guard

Even with `temperature=0`, Gemini can sometimes produce inconsistent outputs.

Add a **deterministic retry guard** for all LLM responses.

Create helper inside each agent file:

```python
def _llm_with_validation(prompt: str, max_attempts: int = 3) -> str:
    """
    Call LLM and validate response structure.
    Retries if output is malformed.
    """
```

Logic:

```
1. Call LLM
2. Validate response
3. If invalid → retry
4. After 3 failures → raise LLMResponseError
```

Example validation rules:

| Agent     | Validation                                   |
| --------- | -------------------------------------------- |
| Ingest    | must contain at least 1 label like `[TITLE]` |
| Parse     | must be valid JSON                           |
| Interpret | must contain `"style_name"`                  |
| Transform | must contain `"docx_instructions"`           |
| Validate  | must contain `"overall_score"`               |

---

# 🎯 IMPROVEMENT 2 — Token Size Protection

Gemini Flash can fail if prompts are too large.

Add **input truncation protection**.

Implement utility in each agent:

```python
def _truncate_input(text: str, max_chars: int = 45000) -> str:
```

Logic:

```
If len(text) > max_chars:
    keep first 35000 chars
    keep last 5000 chars
    insert "[TRUNCATED]"
```

Use in:

```
ingest_agent
parse_agent
transform_agent
validate_agent
```

This prevents **token overflow crashes**.

---

# 🎯 IMPROVEMENT 3 — JSON Schema Validation for Agent Outputs

Create schema validation inside agents to prevent malformed LLM output.

Example for **parse_agent**:

```python
REQUIRED_FIELDS = [
    "title",
    "authors",
    "abstract",
    "sections",
    "references",
    "metadata"
]
```

Add validation function:

```python
def _validate_parse_output(data: dict):
```

If missing fields:

```
raise ParseError("Parse output missing required field: ...")
```

Do similar validation for:

| Agent           | Validation                          |
| --------------- | ----------------------------------- |
| parse_agent     | required JSON fields                |
| transform_agent | `docx_instructions.sections` exists |
| validate_agent  | `overall_score` exists              |
| interpret_agent | rules JSON contains 11 top keys     |

---

# 🎯 IMPROVEMENT 4 — Structured Logging for Agents

Agents currently log minimal info.

Add structured logs for each pipeline stage.

Example:

```python
logger.info(
    "Parse agent extracted paper structure | sections=%s | refs=%s",
    len(structure["sections"]),
    len(structure["references"])
)
```

Recommended logs:

| Agent     | Log                         |
| --------- | --------------------------- |
| Ingest    | labels detected             |
| Parse     | sections / references count |
| Interpret | journal style loaded        |
| Transform | violations count            |
| Validate  | final score                 |

This dramatically improves **debugging during demo**.

---

# 🎯 IMPROVEMENT 5 — Defensive Context Access

CrewAI context passing can occasionally fail.

Example:

```
context["paper_structure"]
```

can raise KeyError.

Replace all direct access with safe accessor.

Create helper:

```python
def _safe_context(context: dict, key: str):
    if key not in context:
        raise ValueError(f"Pipeline context missing required key: {key}")
    return context[key]
```

Use everywhere.

---

# 🎯 IMPROVEMENT 6 — Citation Normalization Utility

Citation patterns vary widely.

Add shared function in **transform_agent**:

```python
def _normalize_citation(citation: str) -> str:
```

Normalize patterns:

```
(Smith et al. 2020)
(Smith, 2020)
[1]
[1,2]
[1-3]
```

Convert to normalized representation before comparison.

This improves:

```
citation_replacements detection
citation consistency scoring
```

---

# 🎯 IMPROVEMENT 7 — Section Ordering Recovery

LLMs sometimes return sections in wrong order.

Add ordering fix in **transform_agent**.

Algorithm:

```
Title
Abstract
Keywords
Introduction
Methods
Results
Discussion
Conclusion
References
```

Sort `docx_instructions.sections` based on this canonical order.

---

# 🎯 IMPROVEMENT 8 — Transform Agent Safety Check

Before returning transform_result:

Verify:

```
docx_instructions exists
docx_instructions["sections"] exists
sections length > 0
```

If not:

```
raise TransformError("Transform output missing sections")
```

This prevents crashes inside:

```
crew._write_docx_from_transform()
```

---

# 🎯 IMPROVEMENT 9 — Validation Agent Score Integrity

Sometimes LLM produces inconsistent scoring.

Add post-check:

```
0 ≤ score ≤ 100
```

Clamp values:

```python
score = max(0, min(100, score))
```

Also recompute **overall_score if breakdown inconsistent**.

---

# 🎯 IMPROVEMENT 10 — Cross-Agent Sanity Checks

Add consistency checks between agents.

Example in **validate_agent**:

```
if paper_structure["metadata"]["total_references"] != len(paper_structure["references"]):
    log warning
```

Example in **transform_agent**:

```
if sections detected by parse_agent == 0:
    raise TransformError("Paper structure invalid")
```

---

# 🎯 IMPROVEMENT 11 — Pipeline Metrics

Add runtime metrics.

Example:

```python
import time
start = time.time()

...

logger.info("Parse agent completed in %.2fs", time.time() - start)
```

Add to all agents.

Useful for **hackathon demo telemetry**.

---

# 🎯 IMPROVEMENT 12 — Lightweight Caching (Interpret Agent)

Journal rules never change during runtime.

Add cache:

```python
_RULE_ENGINE_CACHE = {}
```

Logic:

```
if journal_style in cache:
    return cached rules
else:
    load_rules()
    cache
```

Speeds up repeated runs.

---

# 🎯 EXPECTED FINAL RESULT

After improvements your agents should be:

```
Deterministic
Token-safe
Schema validated
Crash-resistant
Logged
Fast
```

Your agents folder remains:

```
backend/agents/
├── ingest_agent.py
├── parse_agent.py
├── interpret_agent.py
├── transform_agent.py
└── validate_agent.py
```

No new agent files required.

---

# OUTPUT REQUIRED

Return **only the modified code sections** for:

```
ingest_agent.py
parse_agent.py
interpret_agent.py
transform_agent.py
validate_agent.py
```

Do not remove existing logic — only **enhance robustness and validation**.
