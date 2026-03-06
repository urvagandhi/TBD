import json
import logging
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

load_dotenv(override=True)

_API_START_TIME = time.time()
MAX_PIPELINE_RUNTIME = 300  # seconds — log warning if pipeline exceeds this

# ---------------------------------------------------------------------------
# Logging — configure root logger once at process start
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

from crew import run_pipeline
from tools.docx_reader import extract_docx_text
from tools.logger import get_logger
from tools.pdf_reader import extract_pdf_text
from tools.pre_format_scorer import score_pre_format
from tools.rule_loader import JOURNAL_MAP, get_supported_journals, load_rules
from tools.tool_errors import (
    DocumentWriteError,
    LLMResponseError,
    ParseError,
    RuleLoadError,
    ToolError,
    TransformError,
    ValidationError,
)

logger = get_logger(__name__)

app = FastAPI(
    title="Agent Paperpal API",
    description="Autonomous manuscript formatting system — HackaMined 2026",
    version="2.0.0",
)

# CORS — allow React dev server (Vite + CRA) and configured origins
_cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOADS_DIR = Path(__file__).parent / "uploads"
OUTPUTS_DIR = Path(__file__).parent / "outputs"
RULES_DIR = Path(__file__).parent / "rules"
UPLOADS_DIR.mkdir(exist_ok=True)
OUTPUTS_DIR.mkdir(exist_ok=True)

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
MIN_TEXT_LENGTH = 100
MIN_ALPHA_RATIO = 0.3  # Minimum ratio of alphabetic chars — rejects garbled/scanned text
ALLOWED_EXTENSIONS = {"pdf", "docx", "txt"}
DOC_EXPIRY_SECONDS = 3600  # uploaded docs expire after 1 hour

# ── In-memory stores ─────────────────────────────────────────────────────────
# DOC_STORE: uploaded documents keyed by doc_id
#   { doc_id: { text, ext, filename, upload_path, created_at } }
DOC_STORE: dict = {}

# JOB_STORE: pipeline jobs keyed by job_id
#   { job_id: { status, progress, result?, error?, created_at } }
JOB_STORE: dict = {}


# ---------------------------------------------------------------------------
# Background pipeline worker
# ---------------------------------------------------------------------------
def _run_pipeline_job(
    paper_text: str,
    journal: str,
    job_id: str,
    fidelity_warnings: list,
    source_docx_path: Optional[str] = None,
    overrides: Optional[str] = None,
    custom_rules: Optional[str] = None,
) -> None:
    """
    Background worker for async pipeline processing.
    Writes result into JOB_STORE[job_id] when complete.
    """
    start = time.time()
    logger.info("[JOB:%s] Background pipeline started — journal=%s chars=%d",
                job_id, journal, len(paper_text))

    # Progress callback — updates JOB_STORE in real-time as agents complete
    def _on_progress(step_index, progress, step_name, step_elapsed, total_elapsed):
        job = JOB_STORE.get(job_id)
        if job:
            job["progress"] = progress
            job["step_index"] = step_index  # 1-indexed (completed step)
            job["step_name"] = step_name
            job["step_elapsed"] = step_elapsed
            job["total_elapsed"] = total_elapsed
            logger.info(
                "[JOB:%s] Agent %d/4 (%s) done — %.1fs (total: %.1fs, progress: %d%%)",
                job_id, step_index, step_name, step_elapsed, total_elapsed, progress,
            )

    try:
        JOB_STORE[job_id]["progress"] = 5
        JOB_STORE[job_id]["step_index"] = 0
        JOB_STORE[job_id]["step_name"] = "INGEST"

        # Apply overrides or custom rules before pipeline runs
        rules_override = None
        if custom_rules and custom_rules.strip():
            # Full Custom mode: use LLM-extracted rules directly
            try:
                rules_override = json.loads(custom_rules)
                logger.info("[JOB:%s] Full Custom rules applied — style=%s",
                            job_id, rules_override.get("style_name", "Custom"))
            except (json.JSONDecodeError, TypeError):
                logger.warning("[JOB:%s] Invalid custom_rules JSON, falling back to journal rules", job_id)
        elif overrides and overrides.strip():
            # Semi Custom mode: merge overrides into base journal rules
            merged = _apply_overrides(load_rules(journal), overrides)
            if merged is not None:
                rules_override = merged
                logger.info("[JOB:%s] Semi Custom overrides applied to rules", job_id)

        result = run_pipeline(
            paper_text, journal,
            source_docx_path=source_docx_path,
            rules_override=rules_override,
            progress_callback=_on_progress,
        )
        compliance_report = result["compliance_report"]
        enriched_changes = result.get("changes_made", []) or compliance_report.get("changes_made", [])
        elapsed = round(time.time() - start, 1)
        logger.info("[JOB:%s] Pipeline complete — score=%s elapsed=%.1fs",
                    job_id, compliance_report.get("overall_score", "?"), elapsed)
        JOB_STORE[job_id] = {
            "status": "done",
            "progress": 100,
            "created_at": JOB_STORE[job_id].get("created_at", time.time()),
            "result": {
                "success": True,
                "request_id": job_id,
                "download_url": f"/download/{result['docx_filename']}",
                "preview_url": f"/preview/{result['docx_filename']}",
                "compliance_report": compliance_report,
                "changes_made": enriched_changes,
                "processing_time_seconds": elapsed,
                "output_metadata": result.get("output_metadata", {}),
                "pipeline_metrics": result.get("pipeline_metrics", {}),
                "interpretation_results": result.get("interpretation_results", {}),
                "fidelity_warnings": fidelity_warnings,
                "post_format_score": result.get("post_format_score", {}),
                "formatting_report": result.get("formatting_report", {}),
            },
        }
    except Exception as e:
        logger.exception("[JOB:%s] Background pipeline failed: %s", job_id, e)
        JOB_STORE[job_id] = {
            "status": "error",
            "progress": 0,
            "error": str(e),
            "created_at": JOB_STORE[job_id].get("created_at", time.time()),
        }


# ---------------------------------------------------------------------------
# Cleanup helpers
# ---------------------------------------------------------------------------
def _cleanup_old_outputs(hours: int = 6) -> None:
    """Delete old run folders and loose DOCX files in outputs/ older than `hours` hours."""
    import shutil
    cutoff = time.time() - hours * 3600
    removed = 0
    # Clean run_* subfolders
    for d in OUTPUTS_DIR.glob("run_*"):
        try:
            if d.is_dir() and d.stat().st_mtime < cutoff:
                shutil.rmtree(d)
                removed += 1
        except Exception:
            pass
    # Clean any loose DOCX files (legacy)
    for f in OUTPUTS_DIR.glob("*.docx"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink(missing_ok=True)
                removed += 1
        except Exception:
            pass
    # Clean legacy intermediate_* files
    for f in OUTPUTS_DIR.glob("intermediate_*.txt"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink(missing_ok=True)
                removed += 1
        except Exception:
            pass
    if removed:
        logger.info("[CLEANUP] Removed %d stale output(s) older than %dh", removed, hours)


def _cleanup_expired_docs() -> None:
    """Remove expired documents from DOC_STORE and their upload files."""
    now = time.time()
    expired = [
        doc_id for doc_id, doc in DOC_STORE.items()
        if now - doc.get("created_at", 0) > DOC_EXPIRY_SECONDS
    ]
    for doc_id in expired:
        doc = DOC_STORE.pop(doc_id, {})
        upload_path = doc.get("upload_path")
        if upload_path and Path(upload_path).exists():
            Path(upload_path).unlink(missing_ok=True)
        logger.debug("[CLEANUP] Expired doc_id=%s", doc_id)
    if expired:
        logger.info("[CLEANUP] Removed %d expired document(s)", len(expired))


# ---------------------------------------------------------------------------
# Global exception handler
# ---------------------------------------------------------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("[GLOBAL] Unhandled exception on %s: %s", request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "An unexpected error occurred. Please try again.",
            "step": "unknown",
        },
    )


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def startup_event() -> None:
    logger.info("=" * 50)
    logger.info("Agent Paperpal API v2.0 starting up")
    logger.info("Supported journals: %s", get_supported_journals())
    logger.info("Upload dir:  %s", UPLOADS_DIR.resolve())
    logger.info("Output dir:  %s", OUTPUTS_DIR.resolve())
    if not os.getenv("GEMINI_API_KEY") and not os.getenv("GOOGLE_API_KEY"):
        logger.error("GEMINI_API_KEY not set in environment! LLM calls will fail.")
    else:
        logger.info("GEMINI_API_KEY: set ✓")
    _cleanup_old_outputs(hours=6)
    logger.info("=" * 50)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _get_extension(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _sanitize_filename(filename: str) -> str:
    """Reject any filename with path traversal characters."""
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename.")
    return filename


def _read_text_with_fallback(path: str) -> str:
    """Read a plain text file, trying encodings: UTF-8 → Latin-1 → CP-1252."""
    for encoding in ("utf-8", "latin-1", "cp1252"):
        try:
            with open(path, "r", encoding=encoding) as fh:
                return fh.read()
        except UnicodeDecodeError:
            continue
    raise HTTPException(
        status_code=422,
        detail={
            "success": False,
            "error": "Could not decode the .txt file. Supported encodings: UTF-8, Latin-1, CP-1252.",
            "step": "extraction",
        },
    )


def _extract_text(upload_path: str, ext: str) -> str:
    """Extract text from a file based on its extension."""
    if ext == "pdf":
        return extract_pdf_text(upload_path)
    elif ext == "txt":
        return _read_text_with_fallback(upload_path)
    else:
        return extract_docx_text(upload_path)


def _validate_text_quality(text: str, request_id: str) -> None:
    """Validate extracted text length and quality. Raises HTTPException on failure."""
    stripped = text.strip()
    if len(stripped) < MIN_TEXT_LENGTH:
        logger.warning("[REQUEST:%s] Rejected — text too short (%d chars)", request_id, len(stripped))
        raise HTTPException(
            status_code=422,
            detail={
                "success": False,
                "error": "Extracted text is too short. Ensure the document contains readable text.",
                "step": "extraction",
            },
        )
    total_chars = len(stripped)
    if total_chars > 0:
        alpha_ratio = sum(c.isalpha() for c in stripped) / total_chars
        if alpha_ratio < MIN_ALPHA_RATIO:
            logger.warning("[REQUEST:%s] Rejected — low alpha ratio %.2f", request_id, alpha_ratio)
            raise HTTPException(
                status_code=422,
                detail={
                    "success": False,
                    "error": "Extracted text appears corrupted or is primarily non-alphabetic.",
                    "step": "extraction",
                },
            )


def _get_doc_or_404(doc_id: str) -> dict:
    """Retrieve a document from DOC_STORE or raise 404."""
    doc = DOC_STORE.get(doc_id)
    if not doc:
        raise HTTPException(
            status_code=404,
            detail={
                "success": False,
                "error": f"Document '{doc_id}' not found. It may have expired (1 hour TTL). Please re-upload.",
            },
        )
    return doc


def _get_fidelity_warnings(ext: str) -> list:
    """Return fidelity warnings based on file type."""
    if ext == "pdf":
        return [
            "PDF input: figures, tables, and equations cannot be preserved in the output DOCX. "
            "Upload the original .docx file for full-fidelity transformation."
        ]
    elif ext == "txt":
        return [
            "Plain text input: document formatting and embedded objects cannot be recovered. "
            "Upload the original .docx file for full-fidelity transformation."
        ]
    return []


def _apply_overrides(rules: dict, overrides: str) -> dict:
    """
    Apply Semi Custom structured overrides to journal rules.

    Accepts a JSON string of structured overrides (e.g. {"document": {"font": "Arial"}})
    and merges validated fields into the rules dict.
    """
    if not overrides or not overrides.strip():
        return rules

    try:
        overrides_json = json.loads(overrides)
    except (json.JSONDecodeError, TypeError):
        logger.warning("[OVERRIDES] Invalid JSON in overrides, ignoring: %s", overrides[:100])
        return rules

    if not isinstance(overrides_json, dict):
        return rules

    rules = json.loads(json.dumps(rules))  # deep copy

    # Validate and apply only allowed fields
    applied, _blocked, _errors = _validate_overrides(overrides_json)
    for item in applied:
        section, field = item["field"].split(".", 1)
        rules.setdefault(section, {})[field] = item["value"]

    logger.info("[OVERRIDES] Applied structured overrides")
    return rules


# ---------------------------------------------------------------------------
# Structured override validation — SOFT allowlist with enums/ranges
# ---------------------------------------------------------------------------
OVERRIDE_SCHEMA = {
    "abstract.max_words": {
        "type": "int", "min": 50, "max": 1000,
        "label": "Abstract Word Limit",
    },
    "document.font": {
        "type": "enum",
        "values": ["Times New Roman", "Arial", "Calibri", "Georgia"],
        "label": "Font Family",
    },
    "document.font_size": {
        "type": "enum_int",
        "values": [8, 9, 10, 11, 12, 14, 16],
        "label": "Font Size",
    },
    "document.line_spacing": {
        "type": "enum_float",
        "values": [1.0, 1.15, 1.5, 2.0],
        "label": "Line Spacing",
    },
    "headings.numbering_style": {
        "type": "enum",
        "values": ["roman", "numeric", "alpha"],
        "label": "Heading Numbering",
    },
    "references.style": {
        "type": "enum",
        "values": ["ieee", "apa", "mla", "chicago", "vancouver"],
        "label": "Reference Style",
    },
    "figures.caption_position": {
        "type": "enum",
        "values": ["below", "above"],
        "label": "Figure Caption Position",
    },
    "tables.caption_position": {
        "type": "enum",
        "values": ["above", "below"],
        "label": "Table Caption Position",
    },
}

# HARD fields — not exposed to user, rejected if submitted
HARD_BLOCKED_FIELDS = {
    "citations.style",
    "citations.brackets",
    "mandatory_sections",
}


def _validate_overrides(overrides_json: dict) -> tuple:
    """
    Validate structured overrides against the allowlist.

    Args:
        overrides_json: Nested dict like {"document": {"font": "Arial"}, "abstract": {"max_words": 350}}

    Returns:
        (applied, blocked, errors)
        - applied: list of validated {section, field, value, label}
        - blocked: list of {section, field, reason}
        - errors: list of {field, message, allowed} for invalid values
    """
    applied = []
    blocked = []
    errors = []

    for section, fields in overrides_json.items():
        if not isinstance(fields, dict):
            continue
        for field, value in fields.items():
            dotted = f"{section}.{field}"

            # Check HARD blocked
            if dotted in HARD_BLOCKED_FIELDS:
                blocked.append({
                    "field": dotted,
                    "reason": "not_overridable",
                })
                continue

            # Check if in SOFT allowlist
            schema = OVERRIDE_SCHEMA.get(dotted)
            if not schema:
                blocked.append({
                    "field": dotted,
                    "reason": "not_overridable",
                })
                continue

            # Validate value
            if schema["type"] == "int":
                try:
                    val = int(value)
                except (ValueError, TypeError):
                    errors.append({"field": dotted, "message": f"Must be an integer", "allowed": f"{schema['min']}–{schema['max']}"})
                    continue
                if val < schema["min"] or val > schema["max"]:
                    errors.append({"field": dotted, "message": f"Out of range", "allowed": f"{schema['min']}–{schema['max']}"})
                    continue

            elif schema["type"] == "enum":
                if value not in schema["values"]:
                    errors.append({"field": dotted, "message": f"Invalid value", "allowed": schema["values"]})
                    continue

            elif schema["type"] == "enum_int":
                try:
                    val = int(value)
                except (ValueError, TypeError):
                    errors.append({"field": dotted, "message": f"Must be an integer", "allowed": schema["values"]})
                    continue
                if val not in schema["values"]:
                    errors.append({"field": dotted, "message": f"Invalid value", "allowed": schema["values"]})
                    continue

            elif schema["type"] == "enum_float":
                try:
                    val = float(value)
                except (ValueError, TypeError):
                    errors.append({"field": dotted, "message": f"Must be a number", "allowed": schema["values"]})
                    continue
                if val not in schema["values"]:
                    errors.append({"field": dotted, "message": f"Invalid value", "allowed": schema["values"]})
                    continue

            applied.append({
                "field": dotted,
                "value": value,
                "label": schema["label"],
            })

    return applied, blocked, errors


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------
@app.get("/health")
async def health() -> dict:
    """Health check — returns API status, diagnostics, and supported journals."""
    rules_dir = Path(__file__).parent / "rules"
    outputs_writable = os.access(OUTPUTS_DIR, os.W_OK)
    rules_exists = rules_dir.exists()
    status = "ok" if (outputs_writable and rules_exists) else "degraded"

    try:
        import crewai
        crewai_version = crewai.__version__
    except Exception:
        crewai_version = "unknown"

    logger.info("[HEALTH] GET /health — status=%s", status)
    return {
        "status": status,
        "version": "2.0.0",
        "service": "Agent Paperpal",
        "supported_journals": get_supported_journals(),
        "max_file_size_mb": MAX_FILE_SIZE // (1024 * 1024),
        "supported_modes": ["standard", "semi_custom", "full_custom"],
        "system_info": {
            "python_version": sys.version.split()[0],
            "crewai_version": crewai_version,
            "api_uptime_seconds": round(time.time() - _API_START_TIME, 1),
        },
        "diagnostics": {
            "rules_folder_exists": rules_exists,
            "outputs_folder_writable": outputs_writable,
            "active_docs": len(DOC_STORE),
            "active_jobs": len([j for j in JOB_STORE.values() if j.get("status") == "processing"]),
        },
    }


# ---------------------------------------------------------------------------
# POST /upload — Step 1: Upload file, extract text, return doc_id
# ---------------------------------------------------------------------------
@app.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
) -> JSONResponse:
    """
    Upload a PDF, DOCX, or TXT file. Extracts text and returns a doc_id
    for use in subsequent /score/pre and /format calls.

    Returns:
        { success, doc_id, filename, file_type, char_count, word_count, preview }
    """
    doc_id = uuid.uuid4().hex[:8]
    ext = _get_extension(file.filename or "")

    logger.info("[UPLOAD:%s] POST /upload — file=%s", doc_id, file.filename)

    # Validate extension
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=422, detail={
            "success": False,
            "error": f"Unsupported file type '.{ext}'. Upload a PDF, DOCX, or TXT file.",
            "step": "validation",
        })

    # Read and validate size
    content = await file.read()
    size_kb = round(len(content) / 1024, 1)
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail={
            "success": False,
            "error": f"File exceeds 10 MB limit ({size_kb} KB uploaded).",
            "step": "validation",
        })

    # Save to disk
    safe_name = re.sub(r"[^a-zA-Z0-9._\-]", "_", file.filename or "upload")
    upload_filename = f"{doc_id}_{safe_name}"
    upload_path = UPLOADS_DIR / upload_filename

    try:
        upload_path.write_bytes(content)

        # Extract text
        logger.info("[UPLOAD:%s] Extracting text from %s (%sKB)...", doc_id, ext.upper(), size_kb)
        t0 = time.time()
        paper_text = _extract_text(str(upload_path), ext)
        extract_time = round(time.time() - t0, 2)
        logger.info("[UPLOAD:%s] Extracted %d chars in %.2fs", doc_id, len(paper_text), extract_time)

        # Validate text quality
        _validate_text_quality(paper_text, doc_id)

        # Store in DOC_STORE
        DOC_STORE[doc_id] = {
            "text": paper_text,
            "ext": ext,
            "filename": file.filename,
            "upload_path": str(upload_path),
            "size_kb": size_kb,
            "created_at": time.time(),
        }

        # Cleanup expired docs periodically
        _cleanup_expired_docs()

        # Generate preview (first 500 chars)
        preview = paper_text[:500] + ("..." if len(paper_text) > 500 else "")
        word_count = len(paper_text.split())

        logger.info("[UPLOAD:%s] Document stored — words=%d ext=%s", doc_id, word_count, ext)

        return JSONResponse(status_code=200, content={
            "success": True,
            "doc_id": doc_id,
            "filename": file.filename,
            "file_type": ext,
            "char_count": len(paper_text),
            "word_count": word_count,
            "size_kb": size_kb,
            "preview": preview,
        })

    except HTTPException:
        # Clean up on validation failure
        if upload_path.exists():
            upload_path.unlink(missing_ok=True)
        raise

    except Exception as e:
        if upload_path.exists():
            upload_path.unlink(missing_ok=True)
        logger.exception("[UPLOAD:%s] Error: %s", doc_id, e)
        raise HTTPException(status_code=500, detail={
            "success": False,
            "error": "Failed to process uploaded file. Please try again.",
            "step": "upload",
        })


# ---------------------------------------------------------------------------
# POST /score/pre — Step 2: Pre-format compliance score
# ---------------------------------------------------------------------------
@app.post("/score/pre")
async def score_pre(
    doc_id: str = Form(...),
    journal: str = Form(...),
    mode: str = Form("standard"),
    overrides: str = Form(""),
    custom_rules: str = Form(""),
) -> JSONResponse:
    """
    Score the uploaded document against journal rules BEFORE formatting.

    Args:
        doc_id: Document ID from /upload
        journal: Target journal style (e.g. "APA 7th Edition")
        mode: "standard" | "semi_custom" | "full_custom"
        overrides: NL-based overrides for semi_custom mode
        custom_rules: Full custom rules JSON for full_custom mode

    Returns:
        { success, doc_id, journal, mode, pre_format_score }
    """
    logger.info("[PRE-SCORE:%s] POST /score/pre — journal=%s mode=%s", doc_id, journal, mode)

    # Validate doc_id
    doc = _get_doc_or_404(doc_id)

    # Validate journal (skip for full_custom with custom_rules)
    if not (mode == "full_custom" and custom_rules and custom_rules.strip()):
        if journal.lower().strip() not in JOURNAL_MAP:
            raise HTTPException(status_code=422, detail={
                "success": False,
                "error": f"Unsupported journal '{journal}'.",
                "supported_journals": get_supported_journals(),
                "step": "validation",
            })

    # Validate mode
    if mode not in ("standard", "semi_custom", "full_custom"):
        raise HTTPException(status_code=422, detail={
            "success": False,
            "error": f"Invalid mode '{mode}'. Must be: standard, semi_custom, or full_custom.",
            "step": "validation",
        })

    try:
        # Determine rules source based on mode
        if mode == "full_custom" and custom_rules and custom_rules.strip():
            try:
                rules = json.loads(custom_rules)
                logger.info("[PRE-SCORE:%s] Using custom rules (%d keys)", doc_id, len(rules))
            except (json.JSONDecodeError, TypeError):
                logger.warning("[PRE-SCORE:%s] Invalid custom_rules JSON, falling back", doc_id)
                rules = load_rules(journal)
        else:
            rules = load_rules(journal)

        # Apply overrides for semi_custom mode
        if mode == "semi_custom" and overrides:
            rules = _apply_overrides(rules, overrides)

        result = score_pre_format(doc["text"], rules)

        logger.info("[PRE-SCORE:%s] Score=%d", doc_id, result["total_score"])

        return JSONResponse(status_code=200, content={
            "success": True,
            "doc_id": doc_id,
            "journal": journal,
            "mode": mode,
            "pre_format_score": result,
        })

    except RuleLoadError as e:
        raise HTTPException(status_code=422, detail={
            "success": False, "error": str(e), "step": "rules",
        })
    except Exception as e:
        logger.exception("[PRE-SCORE:%s] Error: %s", doc_id, e)
        raise HTTPException(status_code=500, detail={
            "success": False, "error": "Pre-check failed. Please try again.", "step": "pre-check",
        })


# ---------------------------------------------------------------------------
# GET /journal-defaults/{journal} — Return overridable field defaults
# ---------------------------------------------------------------------------
@app.get("/journal-defaults/{journal}")
async def get_journal_defaults(journal: str) -> JSONResponse:
    """
    Return the current default values for all overridable fields
    for a given journal style. Used by the Semi Custom panel to
    show placeholders/defaults.
    """
    if journal.lower().strip() not in JOURNAL_MAP:
        raise HTTPException(status_code=422, detail={
            "success": False,
            "error": f"Unsupported journal '{journal}'.",
            "supported_journals": get_supported_journals(),
        })

    rules = load_rules(journal)
    defaults = {}
    for dotted in OVERRIDE_SCHEMA:
        section, field = dotted.split(".", 1)
        val = rules.get(section, {}).get(field)
        if val is not None:
            defaults[dotted] = val

    return JSONResponse(status_code=200, content={
        "journal": journal,
        "style_name": rules.get("style_name", journal),
        "defaults": defaults,
        "schema": {k: {"label": v["label"], "type": v["type"],
                        "values": v.get("values"), "min": v.get("min"), "max": v.get("max")}
                   for k, v in OVERRIDE_SCHEMA.items()},
    })


# ---------------------------------------------------------------------------
# POST /format — Step 3: Trigger full CrewAI pipeline (always async)
# ---------------------------------------------------------------------------
@app.post("/format")
async def format_document(
    background_tasks: BackgroundTasks,
    doc_id: str = Form(None),
    journal: str = Form(...),
    mode: str = Form("standard"),
    overrides: str = Form(""),
    custom_rules: str = Form(""),
    # Legacy support: also accept file upload directly
    file: Optional[UploadFile] = File(None),
    guideline_pdf: Optional[UploadFile] = File(None),
) -> JSONResponse:
    """
    Trigger the full CrewAI formatting pipeline.

    Accepts either:
      - doc_id (from /upload) — preferred, avoids re-uploading
      - file (multipart) — legacy support, uploads inline

    Args:
        doc_id: Document ID from /upload (preferred)
        journal: Target journal style
        mode: "standard" | "semi_custom" | "full_custom"
        overrides: NL-based overrides for semi_custom mode
        file: Direct file upload (legacy — use /upload + doc_id instead)
        guideline_pdf: Custom guidelines PDF for full_custom mode

    Returns:
        { success, job_id, status, poll_url }
    """
    job_id = uuid.uuid4().hex[:8]

    # ── Resolve document text ─────────────────────────────────────────────
    paper_text = None
    ext = None
    source_docx_path = None
    original_filename = None

    if doc_id:
        # Preferred path: use pre-uploaded document
        doc = _get_doc_or_404(doc_id)
        paper_text = doc["text"]
        ext = doc["ext"]
        original_filename = doc.get("filename", "document")
        # Provide source DOCX path for in-place transformation
        if ext == "docx" and doc.get("upload_path") and Path(doc["upload_path"]).exists():
            source_docx_path = doc["upload_path"]
        logger.info("[FORMAT:%s] Using pre-uploaded doc_id=%s (%s)", job_id, doc_id, ext)

    elif file:
        # Legacy path: inline file upload
        ext = _get_extension(file.filename or "")
        original_filename = file.filename

        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=422, detail={
                "success": False,
                "error": f"Unsupported file type '.{ext}'. Upload a PDF or DOCX.",
                "step": "validation",
            })

        content = await file.read()
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail={
                "success": False,
                "error": f"File exceeds 10 MB limit.",
                "step": "validation",
            })

        # Save and extract
        safe_name = re.sub(r"[^a-zA-Z0-9._\-]", "_", file.filename or "upload")
        upload_path = UPLOADS_DIR / f"{job_id}_{safe_name}"
        upload_path.write_bytes(content)

        try:
            paper_text = _extract_text(str(upload_path), ext)
            _validate_text_quality(paper_text, job_id)
            if ext == "docx":
                source_docx_path = str(upload_path)
        except Exception:
            if upload_path.exists():
                upload_path.unlink(missing_ok=True)
            raise

        logger.info("[FORMAT:%s] Using inline file upload (%s)", job_id, ext)
    else:
        raise HTTPException(status_code=422, detail={
            "success": False,
            "error": "Either doc_id or file must be provided.",
            "step": "validation",
        })

    # ── Validate journal (skip for full_custom with custom_rules) ────────
    if not (mode == "full_custom" and custom_rules and custom_rules.strip()):
        if journal.lower().strip() not in JOURNAL_MAP:
            raise HTTPException(status_code=422, detail={
                "success": False,
                "error": f"Unsupported journal '{journal}'.",
                "supported_journals": get_supported_journals(),
                "step": "validation",
            })

    # ── Validate mode ─────────────────────────────────────────────────────
    if mode not in ("standard", "semi_custom", "full_custom"):
        raise HTTPException(status_code=422, detail={
            "success": False,
            "error": f"Invalid mode '{mode}'. Must be: standard, semi_custom, or full_custom.",
            "step": "validation",
        })

    # ── Handle full_custom guideline PDF ──────────────────────────────────
    guideline_text = None
    if mode == "full_custom" and guideline_pdf:
        gl_ext = _get_extension(guideline_pdf.filename or "")
        if gl_ext not in ("pdf", "docx", "txt"):
            raise HTTPException(status_code=422, detail={
                "success": False,
                "error": "Guideline file must be PDF, DOCX, or TXT.",
                "step": "validation",
            })
        gl_content = await guideline_pdf.read()
        gl_path = UPLOADS_DIR / f"{job_id}_guideline.{gl_ext}"
        try:
            gl_path.write_bytes(gl_content)
            guideline_text = _extract_text(str(gl_path), gl_ext)
            logger.info("[FORMAT:%s] Guideline PDF extracted — %d chars", job_id, len(guideline_text))
        except Exception as e:
            logger.warning("[FORMAT:%s] Guideline extraction failed: %s", job_id, e)
        finally:
            if gl_path.exists():
                gl_path.unlink(missing_ok=True)

    # ── Fidelity warnings ─────────────────────────────────────────────────
    fidelity_warnings = _get_fidelity_warnings(ext)

    # ── Create job and start background processing ────────────────────────
    JOB_STORE[job_id] = {
        "status": "processing",
        "progress": 0,
        "created_at": time.time(),
        "journal": journal,
        "mode": mode,
        "filename": original_filename,
    }

    logger.info(
        "[FORMAT:%s] Pipeline queued — journal=%s mode=%s chars=%d",
        job_id, journal, mode, len(paper_text),
    )

    background_tasks.add_task(
        _run_pipeline_job,
        paper_text, journal, job_id, fidelity_warnings,
        source_docx_path=source_docx_path,
        overrides=overrides,
        custom_rules=custom_rules,
    )

    return JSONResponse(
        status_code=202,
        content={
            "success": True,
            "job_id": job_id,
            "status": "processing",
            "poll_url": f"/format/status/{job_id}",
            "message": f"Pipeline started. Poll /format/status/{job_id} for progress.",
        },
    )


# ---------------------------------------------------------------------------
# GET /format/status/{job_id} — Poll pipeline progress
# ---------------------------------------------------------------------------
@app.get("/format/status/{job_id}")
async def get_format_status(job_id: str) -> JSONResponse:
    """
    Poll endpoint for pipeline job status.

    Returns:
        { status, progress, message }
        - status: "processing" | "done" | "error"
        - progress: 0-100 (estimated)
    """
    if not re.match(r"^[a-f0-9]{8}$", job_id):
        raise HTTPException(status_code=400, detail={
            "success": False, "error": "Invalid job_id format.",
        })

    job = JOB_STORE.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail={
            "success": False,
            "error": f"Job '{job_id}' not found. It may have expired or never existed.",
        })

    status = job.get("status", "processing")
    progress = job.get("progress", 0)

    # Agent step names matching frontend ProgressScreen STEPS array
    _STEP_LABELS = [
        "Extracting structure...",
        "Applying format rules...",
        "Validating citations...",
        "Generating document...",
    ]

    # Use real step data from JOB_STORE (set by progress_callback)
    # step_index in JOB_STORE = last completed step (1-indexed), so current = that value
    real_step_index = job.get("step_index", 0)  # 0 = none completed yet
    step_index = real_step_index  # frontend expects 0-indexed "current active step"
    step_name = (
        _STEP_LABELS[step_index]
        if step_index < len(_STEP_LABELS)
        else _STEP_LABELS[-1]
    )

    elapsed = time.time() - job.get("created_at", time.time())

    if status == "processing":
        # Use real progress from callback, but ensure it doesn't go backwards.
        # If callback hasn't fired yet, estimate minimally from elapsed time.
        if progress < 5:
            # Pre-first-agent: show small progress so UI doesn't look stuck
            progress = min(15, max(5, int(elapsed / 30 * 15)))

    response = {
        "status": status,
        "progress": progress,
        "job_id": job_id,
        "step": step_name,
        "step_index": step_index,
        "total_steps": len(_STEP_LABELS),
        "elapsed_seconds": round(elapsed, 1),
    }

    if status == "processing":
        response["message"] = step_name
    elif status == "done":
        response["message"] = "Formatting complete. Fetch results at /format/result/{job_id}"
        response["result_url"] = f"/format/result/{job_id}"
    elif status == "error":
        response["message"] = job.get("error", "Pipeline failed.")
        response["error"] = job.get("error", "Unknown error.")

    return JSONResponse(
        status_code=200,
        content=response,
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
    )


# ---------------------------------------------------------------------------
# GET /format/result/{job_id} — Full pipeline results
# ---------------------------------------------------------------------------
@app.get("/format/result/{job_id}")
async def get_format_result(job_id: str) -> JSONResponse:
    """
    Retrieve the full result of a completed pipeline job.

    Returns:
        {
            success, download_url, compliance_report, changes_made,
            post_format_score, formatting_report, processing_time_seconds,
            output_metadata, pipeline_metrics, fidelity_warnings
        }
    """
    if not re.match(r"^[a-f0-9]{8}$", job_id):
        raise HTTPException(status_code=400, detail={
            "success": False, "error": "Invalid job_id format.",
        })

    job = JOB_STORE.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail={
            "success": False,
            "error": f"Job '{job_id}' not found.",
        })

    status = job.get("status")

    if status == "processing":
        return JSONResponse(status_code=202, content={
            "success": False,
            "status": "processing",
            "message": "Pipeline is still running. Poll /format/status/{job_id} for progress.",
        })

    if status == "error":
        return JSONResponse(status_code=422, content={
            "success": False,
            "status": "error",
            "error": job.get("error", "Pipeline failed."),
        })

    # status == "done"
    result = job.get("result", {})
    return JSONResponse(status_code=200, content=result)


# ---------------------------------------------------------------------------
# GET /download/{filename} — Download formatted DOCX or PDF
# ---------------------------------------------------------------------------
def _convert_docx_to_pdf(docx_path: Path) -> Path:
    """Convert DOCX to PDF using LibreOffice headless. Returns path to PDF."""
    pdf_path = docx_path.with_suffix(".pdf")
    if pdf_path.exists():
        return pdf_path
    try:
        result = subprocess.run(
            ["libreoffice", "--headless", "--convert-to", "pdf",
             "--outdir", str(docx_path.parent), str(docx_path)],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            logger.warning("[PDF] LibreOffice conversion failed: %s", result.stderr)
            raise RuntimeError(f"PDF conversion failed: {result.stderr[:200]}")
        if not pdf_path.exists():
            raise RuntimeError("PDF file was not created by LibreOffice.")
        logger.info("[PDF] Converted %s → %s", docx_path.name, pdf_path.name)
        return pdf_path
    except FileNotFoundError:
        raise RuntimeError("LibreOffice not installed. Cannot convert to PDF.")
    except subprocess.TimeoutExpired:
        raise RuntimeError("PDF conversion timed out.")


@app.get("/download/{filepath:path}")
async def download_file(filepath: str, format: str = "docx") -> FileResponse:
    """Download the formatted file as DOCX or PDF."""
    # filepath can be "formatted_xxx.docx" or "run_xxx/formatted_xxx.docx"
    if not re.match(r"^[a-zA-Z0-9_\-\./]+$", filepath):
        raise HTTPException(status_code=400, detail={
            "success": False, "error": "Invalid filename format.",
        })

    if not filepath.endswith(".docx"):
        raise HTTPException(status_code=400, detail={
            "success": False, "error": "Only .docx files can be downloaded.",
        })

    file_path = (OUTPUTS_DIR / filepath).resolve()
    if not str(file_path).startswith(str(OUTPUTS_DIR.resolve())):
        raise HTTPException(status_code=403, detail={
            "success": False, "error": "Access denied.",
        })

    if not file_path.exists():
        raise HTTPException(status_code=404, detail={
            "success": False,
            "error": f"File '{filepath}' not found or has already been deleted.",
        })

    # Use just the basename for Content-Disposition headers
    dl_name = Path(filepath).name

    if format == "pdf":
        try:
            pdf_path = _convert_docx_to_pdf(file_path)
            pdf_name = dl_name.replace(".docx", ".pdf")
            return FileResponse(
                path=str(pdf_path),
                filename=pdf_name,
                media_type="application/pdf",
                headers={"Content-Disposition": f'attachment; filename="{pdf_name}"'},
            )
        except RuntimeError as e:
            raise HTTPException(status_code=500, detail={
                "success": False, "error": str(e),
            })

    return FileResponse(
        path=str(file_path),
        filename=dl_name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{dl_name}"'},
    )


# ---------------------------------------------------------------------------
# GET /preview/{filename} — Live HTML preview of formatted DOCX
# ---------------------------------------------------------------------------
@app.get("/preview/{filepath:path}")
async def preview_file(filepath: str) -> HTMLResponse:
    """Convert DOCX to HTML for live iframe preview."""
    if not re.match(r"^[a-zA-Z0-9_\-\./]+$", filepath):
        raise HTTPException(status_code=400, detail="Invalid filename format.")

    if not filepath.endswith(".docx"):
        raise HTTPException(status_code=400, detail="Only .docx files can be previewed.")

    file_path = (OUTPUTS_DIR / filepath).resolve()
    if not str(file_path).startswith(str(OUTPUTS_DIR.resolve())):
        raise HTTPException(status_code=403, detail="Access denied.")

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found.")

    try:
        import mammoth
        from docx import Document as DocxDocument

        # Detect column count from DOCX section properties
        num_columns = 1
        try:
            doc = DocxDocument(str(file_path))
            sect = doc.sections[0]
            cols_list = sect._sectPr.xpath('./w:cols')
            if cols_list:
                col_num = cols_list[0].get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}num')
                if col_num and int(col_num) > 1:
                    num_columns = int(col_num)
        except Exception:
            pass

        with open(file_path, "rb") as f:
            result = mammoth.convert_to_html(f)
        html_body = result.value

        # Column CSS: apply multi-column layout for IEEE-style 2-column papers
        if num_columns >= 2:
            col_css = f"""
  .page-body {{
    column-count: {num_columns};
    column-gap: 24px;
    column-rule: 1px solid #e0e0e0;
  }}
  .page-body h1, .page-body h2 {{
    column-span: all;
  }}
  .page-body p, .page-body li {{
    text-align: justify;
    orphans: 3;
    widows: 3;
  }}
  .page {{
    max-width: 900px;
    padding: 54px 54px 60px;
    font-size: 10pt;
    line-height: 1.15;
  }}"""
        else:
            col_css = ""

        # Wrap in a styled document for iframe display — paper-like appearance
        html_page = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  html, body {{
    height: 100%;
    background: #e8e8e8;
    overflow-y: auto;
    -webkit-overflow-scrolling: touch;
  }}
  body {{
    font-family: 'Times New Roman', 'Times', Georgia, serif;
    font-size: 12pt;
    line-height: 2;
    color: #1a1a1a;
  }}
  .page {{
    max-width: 816px;
    min-height: 1056px;
    margin: 20px auto;
    padding: 72px 72px 80px;
    background: #fff;
    box-shadow: 0 2px 12px rgba(0,0,0,0.12), 0 0 0 1px rgba(0,0,0,0.05);
    border-radius: 2px;
  }}
  h1, h2, h3, h4, h5 {{
    line-height: 1.4;
    margin-top: 1.2em;
    margin-bottom: 0.4em;
    color: #111;
  }}
  h1 {{ font-size: 16pt; text-align: center; margin-bottom: 0.6em; }}
  h2 {{ font-size: 13pt; }}
  h3 {{ font-size: 12pt; font-style: italic; }}
  p {{ margin: 0.5em 0; text-align: justify; }}
  table {{
    border-collapse: collapse;
    width: 100%;
    margin: 1em 0;
    font-size: 10pt;
  }}
  td, th {{
    border: 1px solid #bbb;
    padding: 6px 10px;
    text-align: left;
  }}
  th {{ background: #f0f0f0; font-weight: 700; }}
  img {{ max-width: 100%; height: auto; margin: 0.5em 0; }}
  blockquote {{
    margin: 0.8em 0 0.8em 2em;
    padding-left: 1em;
    border-left: 3px solid #ddd;
    color: #444;
  }}
  sup, sub {{ font-size: 0.75em; }}
  a {{ color: #1a56db; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  ::-webkit-scrollbar {{ width: 8px; }}
  ::-webkit-scrollbar-track {{ background: #e8e8e8; }}
  ::-webkit-scrollbar-thumb {{ background: #bbb; border-radius: 4px; }}
  ::-webkit-scrollbar-thumb:hover {{ background: #999; }}
  {col_css}
</style>
</head>
<body>
<div class="page">
<div class="page-body">
{html_body}
</div>
</div>
</body>
</html>"""
        return HTMLResponse(content=html_page)

    except ImportError:
        raise HTTPException(status_code=500, detail="mammoth not installed for DOCX→HTML preview.")
    except Exception as e:
        logger.exception("[PREVIEW] Error converting %s: %s", filepath, e)
        raise HTTPException(status_code=500, detail=f"Preview generation failed: {str(e)[:200]}")


# ---------------------------------------------------------------------------
# POST /extract-rules — Full Custom: Extract rules from guideline PDF via LLM
# ---------------------------------------------------------------------------
_RULES_EXTRACTION_PROMPT = """You are an expert academic formatting analyst. Given the text of a journal's author guidelines document, extract the formatting rules into a structured JSON object.

You MUST return ONLY a valid JSON object with EXACTLY these 11 top-level keys:
- style_name (string): Name of the formatting style
- document (object): font, font_size, line_spacing, margins (top/bottom/left/right), alignment, columns
- title_page (object): title_case, title_bold, title_centered, title_font_size
- abstract (object): label, label_bold, label_centered, label_italic, max_words, indent_first_line, keywords_present
- headings (object): H1/H2/H3 each with bold, italic, centered, underline, case, numbering, font_size
- citations (object): style (author-date or numbered), brackets, format examples
- references (object): section_label, ordering, hanging_indent, formats for journal_article/book/website
- figures (object): label_prefix, caption_position (above/below), numbering
- tables (object): label_prefix, caption_position, numbering, border_style
- equations (object): numbering, numbering_format
- general_rules (object): doi_format, date_format, et_al_threshold, oxford_comma

IMPORTANT RULES:
- If a specific rule is not mentioned in the guidelines, use sensible academic defaults
- font_size must be an integer (e.g., 12)
- line_spacing must be a float (e.g., 2.0)
- margins should be strings like "1in"
- For headings, numbering should be one of: "none", "roman", "numeric", "alpha"
- For citations style, use "author-date" or "numbered"
- Return ONLY the JSON object, no markdown fences, no explanation

Here is the guideline document text:
"""


@app.post("/extract-rules")
async def extract_rules_from_guidelines(
    guideline_file: UploadFile = File(...),
) -> JSONResponse:
    """
    Full Custom mode: Extract formatting rules from a user-uploaded guideline document.
    Uses Gemini LLM to parse the guideline text into the standard rules JSON schema.
    """
    request_id = uuid.uuid4().hex[:8]
    ext = _get_extension(guideline_file.filename or "")

    logger.info("[EXTRACT-RULES:%s] POST /extract-rules — file=%s", request_id, guideline_file.filename)

    if ext not in ("pdf", "docx", "txt"):
        raise HTTPException(status_code=422, detail={
            "success": False,
            "error": "Guideline file must be PDF, DOCX, or TXT.",
        })

    content = await guideline_file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail={
            "success": False, "error": "File exceeds 10 MB limit.",
        })

    gl_path = UPLOADS_DIR / f"{request_id}_guideline.{ext}"
    try:
        gl_path.write_bytes(content)
        guideline_text = _extract_text(str(gl_path), ext)

        if len(guideline_text.strip()) < 50:
            raise HTTPException(status_code=422, detail={
                "success": False,
                "error": "Guideline document is too short or empty.",
            })

        logger.info("[EXTRACT-RULES:%s] Extracted %d chars from guideline", request_id, len(guideline_text))

        # Call Gemini to extract rules
        import google.generativeai as genai

        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise HTTPException(status_code=500, detail={
                "success": False, "error": "LLM API key not configured.",
            })

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite"))

        # Truncate very long guidelines to avoid token limits
        max_chars = 30000
        truncated = guideline_text[:max_chars]
        if len(guideline_text) > max_chars:
            truncated += "\n\n[... document truncated for processing ...]"

        response = model.generate_content(
            _RULES_EXTRACTION_PROMPT + truncated,
            generation_config=genai.types.GenerationConfig(
                temperature=0,
                max_output_tokens=8192,
            ),
        )

        raw_text = response.text.strip()

        # Extract JSON from response (handle markdown fences)
        json_text = raw_text
        if "```json" in json_text:
            json_text = json_text.split("```json", 1)[1].split("```", 1)[0].strip()
        elif "```" in json_text:
            json_text = json_text.split("```", 1)[1].split("```", 1)[0].strip()

        rules = json.loads(json_text)

        # Validate required keys
        required_keys = [
            "style_name", "document", "abstract", "headings",
            "citations", "references", "figures", "tables",
            "general_rules",
        ]
        missing = [k for k in required_keys if k not in rules]
        if missing:
            logger.warning("[EXTRACT-RULES:%s] LLM output missing keys: %s", request_id, missing)
            # Fill in missing keys with defaults
            defaults = json.loads((RULES_DIR / "apa7.json").read_text())
            for k in missing:
                rules[k] = defaults.get(k, {})

        # Ensure title_page and equations exist
        if "title_page" not in rules:
            rules["title_page"] = {"title_case": "Title Case", "title_bold": True, "title_centered": True, "title_font_size": 12}
        if "equations" not in rules:
            rules["equations"] = {"numbering": "right_aligned", "numbering_format": "(1)"}

        logger.info("[EXTRACT-RULES:%s] Rules extracted — style=%s keys=%d",
                    request_id, rules.get("style_name", "Custom"), len(rules))

        return JSONResponse(status_code=200, content={
            "success": True,
            "rules": rules,
            "style_name": rules.get("style_name", "Custom Guidelines"),
        })

    except json.JSONDecodeError as e:
        logger.warning("[EXTRACT-RULES:%s] LLM returned invalid JSON: %s", request_id, e)
        raise HTTPException(status_code=422, detail={
            "success": False,
            "error": "Failed to extract structured rules from the guideline. The AI could not parse the document format. Please try a clearer guideline document.",
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("[EXTRACT-RULES:%s] Error: %s", request_id, e)
        raise HTTPException(status_code=500, detail={
            "success": False,
            "error": f"Rule extraction failed: {str(e)[:200]}",
        })
    finally:
        if gl_path.exists():
            gl_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Helper: Rules dir path (defined near UPLOADS_DIR / OUTPUTS_DIR above)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Legacy endpoints — backward compatibility with existing frontend
# ---------------------------------------------------------------------------
@app.post("/pre-check")
async def pre_check_legacy(
    file: UploadFile = File(...),
    journal: str = Form(...),
) -> JSONResponse:
    """
    Legacy pre-check endpoint. Accepts file + journal directly.
    Prefer /upload + /score/pre for new integrations.
    """
    request_id = uuid.uuid4().hex[:8]
    ext = _get_extension(file.filename or "")

    logger.info("[PRE-CHECK:%s] POST /pre-check (legacy) — file=%s journal=%s",
                request_id, file.filename, journal)

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=422, detail={
            "success": False, "error": f"Unsupported file type '.{ext}'.", "step": "validation",
        })

    if journal.lower().strip() not in JOURNAL_MAP:
        raise HTTPException(status_code=422, detail={
            "success": False, "error": f"Unsupported journal '{journal}'.",
            "supported_journals": get_supported_journals(), "step": "validation",
        })

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail={
            "success": False, "error": "File exceeds 10 MB limit.", "step": "validation",
        })

    upload_path = UPLOADS_DIR / f"{request_id}_precheck"
    try:
        upload_path.write_bytes(content)
        paper_text = _extract_text(str(upload_path), ext)
        _validate_text_quality(paper_text, request_id)
        rules = load_rules(journal)
        result = score_pre_format(paper_text, rules)

        logger.info("[PRE-CHECK:%s] Score=%d", request_id, result["total_score"])
        return JSONResponse(status_code=200, content={
            "success": True, "pre_format_score": result,
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("[PRE-CHECK:%s] Error: %s", request_id, e)
        raise HTTPException(status_code=500, detail={
            "success": False, "error": "Pre-check failed.", "step": "pre-check",
        })
    finally:
        if upload_path.exists():
            upload_path.unlink(missing_ok=True)


@app.get("/status/{job_id}")
async def get_job_status_legacy(job_id: str) -> JSONResponse:
    """Legacy status endpoint. Redirects to /format/status/{job_id}."""
    return await get_format_status(job_id)
