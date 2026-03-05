Below is a **focused improvement prompt only** (not rewriting your tools).
It assumes **Task-3 tools already exist** in your structure and asks Claude to **upgrade them for robustness, performance, and hackathon-grade reliability**.

You can **directly copy-paste this into Claude IDE Extension**.

---

# 🔧 TASK — Improve Tools Layer (Robustness + Performance + Reliability)

You are **NOT building the tools from scratch**.

The following files **already exist**:

```
backend/tools/
├── pdf_reader.py
├── docx_reader.py
├── docx_writer.py
└── rule_loader.py
```

Your task is to **improve the existing implementation only**.

Do **not rewrite the files entirely**.
Refactor and upgrade them while keeping **existing function names and APIs intact**.

The goal is to make the tools **hackathon-ready, robust, and production-quality**.

---

# 🎯 IMPROVEMENT 1 — Unified Error Handling System

Currently each tool likely raises inconsistent errors.

Create a **central error helper**.

Create file:

```
backend/tools/tool_errors.py
```

Implement custom exceptions:

```python
class ToolError(Exception):
    """Base exception for all tool-related errors."""

class FileProcessingError(ToolError):
    """Raised when a file cannot be processed."""

class ExtractionError(ToolError):
    """Raised when text extraction fails."""

class RuleValidationError(ToolError):
    """Raised when formatting rules fail validation."""

class DocumentWriteError(ToolError):
    """Raised when DOCX generation fails."""
```

Update **all tools** to use these instead of generic `ValueError`.

Example:

```python
raise ExtractionError("PDF appears to be scanned. Text extraction not possible.")
```

This makes the **agent layer easier to debug**.

---

# 🎯 IMPROVEMENT 2 — Centralized Logging System

Currently each tool likely creates its own logger.

Create:

```
backend/tools/logger.py
```

Implement:

```python
import logging

def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)

    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
        )
        handler.setFormatter(formatter)

        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

    return logger
```

Update every tool:

```
from .logger import get_logger
logger = get_logger(__name__)
```

Remove any direct `logging.basicConfig()` calls.

---

# 🎯 IMPROVEMENT 3 — Performance Optimization (PDF Extraction)

Improve `pdf_reader.py`.

Add **lazy page processing** instead of loading everything at once.

Current risk:
Large PDFs (100+ pages) may consume too much memory.

Implement:

```python
for page_num in range(page_limit):
    page = doc.load_page(page_num)
    text = page.get_text()
```

Avoid:

```
doc.load_page(i) inside nested loops
```

Also implement **smart page selection**:

```
If pages > 50:
    extract first 30 pages
    extract last 5 pages
```

Add marker:

```
[...TRUNCATED...]
```

This improves **performance dramatically for large submissions**.

---

# 🎯 IMPROVEMENT 4 — Text Quality Detection (Important)

Add a **text quality check** inside both:

```
pdf_reader.py
docx_reader.py
```

Implement function:

```python
def _is_text_garbled(text: str) -> bool:
```

Detect:

• excessive non-ASCII characters
• binary junk
• extremely low word density

Example heuristic:

```
if printable_chars / total_chars < 0.6:
    return True
```

If detected:

```
raise ExtractionError("Extracted text appears corrupted or unreadable.")
```

This prevents agents from receiving **garbage input**.

---

# 🎯 IMPROVEMENT 5 — Smart Header/Footer Detection

Improve `_strip_headers_footers()` in `pdf_reader.py`.

Add logic:

```
Find lines repeated on >50% of pages
Remove them
```

Example headers to remove:

```
Journal of AI Research
Page 3
IEEE Transactions
```

Algorithm:

```
count occurrences of first 2 lines of every page
count occurrences of last 2 lines of every page

if frequency > pages/2 → treat as header/footer
```

This dramatically improves **clean paper parsing**.

---

# 🎯 IMPROVEMENT 6 — DOCX Heading Detection Upgrade

Improve heading detection in `docx_reader.py`.

Current detection likely relies only on style.

Add **heuristics**:

A paragraph is a heading if:

```
style startswith "Heading"
OR
font_size > body_size
OR
bold AND length < 60
OR
ALL CAPS AND length < 60
```

Return:

```
(is_heading, level)
```

Where level inference:

```
Heading 1 → level 1
Heading 2 → level 2
Heading 3 → level 3
Else → infer from font size hierarchy
```

This improves detection for **poorly formatted manuscripts**.

---

# 🎯 IMPROVEMENT 7 — DOCX Writer Safety Mode

Improve `docx_writer.py`.

Add **fail-safe document creation**.

Wrap entire pipeline in:

```python
try:
    ...
except Exception as e:
    logger.error(...)
    return _create_minimal_document(...)
```

Guarantee:

```
write_formatted_docx() ALWAYS produces a valid DOCX
```

Even if instructions fail.

This is **critical for hackathon demos**.

---

# 🎯 IMPROVEMENT 8 — Rule Loader Performance

Improve `rule_loader.py`.

Add **LRU-like caching**.

Current:

```
_RULE_CACHE = {}
```

Enhance with:

```
_schema_cache = None
```

Load schema **once only**.

```python
if _schema_cache is None:
    load schema
```

Avoid repeated disk reads.

---

# 🎯 IMPROVEMENT 9 — Safe Nested Rule Access

Add helper:

```
get_rule_value(rules, key_path)
```

Example usage:

```
get_rule_value(rules, "citations.format_one_author")
```

Implementation:

```
split by "."
walk dictionary safely
return default if missing
```

Replace any direct dictionary access like:

```
rules["citations"]["format_one_author"]
```

with safe access.

This prevents **KeyError crashes**.

---

# 🎯 IMPROVEMENT 10 — Add Lightweight Metrics

Add optional metrics logging to each tool.

Example:

```
logger.info(
    "PDF extraction completed | pages=%s | chars=%s",
    page_count,
    len(text)
)
```

DOCX:

```
logger.info(
    "DOCX parsed | paragraphs=%s | words=%s",
    total_paragraphs,
    total_words
)
```

This makes debugging **extremely easy during demos**.

---

# 🎯 IMPROVEMENT 11 — Add Type Safety

Add stricter type hints.

Example improvements:

```
list[str]
dict[str, Any]
Optional[str]
tuple[bool, int | None]
```

Import:

```
from typing import Any, Optional
```

---

# 🎯 IMPROVEMENT 12 — Thread-Safe Path Handling

Replace any string paths with:

```
Path(filepath)
```

Always resolve:

```
path = Path(filepath).resolve()
```

Prevent relative path issues in FastAPI.

---

# 🎯 FINAL RESULT

After improvements:

```
backend/tools/
├── pdf_reader.py
├── docx_reader.py
├── docx_writer.py
├── rule_loader.py
├── logger.py          ← NEW
└── tool_errors.py     ← NEW
```

Your tools layer will now be:

• robust
• safe
• performant
• debuggable

and suitable for **large academic papers**.

---

# OUTPUT REQUIRED

Return **updated code only for modified sections** of:

```
pdf_reader.py
docx_reader.py
docx_writer.py
rule_loader.py
```

Plus full code for:

```
logger.py
tool_errors.py
```

Do not remove existing functions or break the API used by agents.
