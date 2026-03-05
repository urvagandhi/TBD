import logging
import os
import re
import sys
import time
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

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
from tools.rule_loader import JOURNAL_MAP, get_supported_journals
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
    version="1.0.0",
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
UPLOADS_DIR.mkdir(exist_ok=True)
OUTPUTS_DIR.mkdir(exist_ok=True)

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
MIN_TEXT_LENGTH = 100
MIN_ALPHA_RATIO = 0.3  # Minimum ratio of alphabetic chars — rejects garbled/scanned text
ALLOWED_EXTENSIONS = {"pdf", "docx"}


# ---------------------------------------------------------------------------
# Improvement 10 — Cleanup stale output files on startup
# ---------------------------------------------------------------------------
def _cleanup_old_outputs(hours: int = 6) -> None:
    """Delete DOCX files in outputs/ older than `hours` hours."""
    cutoff = time.time() - hours * 3600
    removed = 0
    for f in OUTPUTS_DIR.glob("*.docx"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink(missing_ok=True)
                removed += 1
        except Exception:
            pass
    if removed:
        logger.info("[CLEANUP] Removed %d stale output file(s) older than %dh", removed, hours)


# ---------------------------------------------------------------------------
# Global exception handler — never expose stack traces to clients
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
# Startup event — verify environment and directories
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def startup_event() -> None:
    logger.info("=" * 50)
    logger.info("Agent Paperpal API starting up")
    logger.info("Supported journals: %s", get_supported_journals())
    logger.info("Upload dir:  %s", UPLOADS_DIR.resolve())
    logger.info("Output dir:  %s", OUTPUTS_DIR.resolve())
    if not os.getenv("GEMINI_API_KEY") and not os.getenv("GOOGLE_API_KEY"):
        logger.error("GEMINI_API_KEY not set in environment! LLM calls will fail.")
    else:
        logger.info("GEMINI_API_KEY: set \u2713")
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
        "version": "1.0.0",
        "service": "Agent Paperpal",
        "supported_journals": get_supported_journals(),
        "max_file_size_mb": MAX_FILE_SIZE // (1024 * 1024),
        "system_info": {
            "python_version": sys.version.split()[0],
            "crewai_version": crewai_version,
            "api_uptime_seconds": round(time.time() - _API_START_TIME, 1),
        },
        "diagnostics": {
            "rules_folder_exists": rules_exists,
            "outputs_folder_writable": outputs_writable,
        },
    }


# ---------------------------------------------------------------------------
# POST /format — main endpoint
# ---------------------------------------------------------------------------
@app.post("/format")
async def format_document(
    file: UploadFile = File(...),
    journal: str = Form(...),
) -> JSONResponse:
    """
    Upload a PDF or DOCX and format it according to the selected journal style.

    Validation order:
      1. File extension (pdf/docx only)
      2. Journal name (must be in JOURNAL_MAP)
      3. File size (<=10 MB)
      4. Extracted text length (>=100 chars)
    """
    request_id = uuid.uuid4().hex[:8]
    ext = _get_extension(file.filename or "")

    logger.info(
        "[REQUEST:%s] POST /format — file=%s journal=%s",
        request_id, file.filename, journal,
    )

    # ── Validation 1: File extension ────────────────────────────────────────
    if ext not in ALLOWED_EXTENSIONS:
        logger.warning("[REQUEST:%s] Rejected — unsupported extension '.%s'", request_id, ext)
        raise HTTPException(
            status_code=422,
            detail={
                "success": False,
                "error": f"Unsupported file type '.{ext}'. Upload a PDF or DOCX.",
                "step": "validation",
            },
        )

    # ── Validation 2: Journal name ───────────────────────────────────────────
    if journal.lower().strip() not in JOURNAL_MAP:
        logger.warning("[REQUEST:%s] Rejected — unknown journal '%s'", request_id, journal)
        raise HTTPException(
            status_code=422,
            detail={
                "success": False,
                "error": f"Unsupported journal '{journal}'.",
                "supported_journals": get_supported_journals(),
                "step": "validation",
            },
        )

    content = await file.read()
    size_kb = round(len(content) / 1024, 1)

    # ── Validation 3: File size ──────────────────────────────────────────────
    if len(content) > MAX_FILE_SIZE:
        logger.warning("[REQUEST:%s] Rejected — file too large (%sKB)", request_id, size_kb)
        raise HTTPException(
            status_code=413,
            detail={
                "success": False,
                "error": f"File exceeds 10 MB limit ({size_kb} KB uploaded).",
                "step": "validation",
            },
        )

    logger.info("[REQUEST:%s] File accepted — size=%sKB type=%s", request_id, size_kb, ext.upper())

    # Improvement 12: Sanitize filename — strip unsafe chars before writing to disk
    safe_name = re.sub(r"[^a-zA-Z0-9._\-]", "_", file.filename or "upload")
    upload_filename = f"{request_id}_{safe_name}"
    upload_path = UPLOADS_DIR / upload_filename

    try:
        upload_path.write_bytes(content)

        # ── Text extraction ──────────────────────────────────────────────────
        logger.info("[REQUEST:%s] Extracting text from %s...", request_id, ext.upper())
        t0 = time.time()
        if ext == "pdf":
            paper_text = extract_pdf_text(str(upload_path))
        else:
            paper_text = extract_docx_text(str(upload_path))
        logger.info(
            "[REQUEST:%s] Text extracted — %d chars in %.2fs",
            request_id, len(paper_text), time.time() - t0,
        )

        # ── Validation 4: Content length ─────────────────────────────────────
        if len(paper_text.strip()) < MIN_TEXT_LENGTH:
            logger.warning(
                "[REQUEST:%s] Rejected — extracted text too short (%d chars)",
                request_id, len(paper_text.strip()),
            )
            raise HTTPException(
                status_code=422,
                detail={
                    "success": False,
                    "error": (
                        "Extracted text is too short. "
                        "Ensure the document contains readable text (not scanned/image-only)."
                    ),
                    "step": "extraction",
                },
            )

        # ── Validation 5: Text quality check (Improvement 16) ────────────────
        stripped = paper_text.strip()
        total_chars = len(stripped)
        if total_chars > 0:
            alpha_ratio = sum(c.isalpha() for c in stripped) / total_chars
            if alpha_ratio < MIN_ALPHA_RATIO:
                logger.warning(
                    "[REQUEST:%s] Rejected — low alpha ratio %.2f (possible garbled/scanned text)",
                    request_id, alpha_ratio,
                )
                raise HTTPException(
                    status_code=422,
                    detail={
                        "success": False,
                        "error": (
                            "Extracted text appears corrupted or is primarily non-alphabetic. "
                            "Ensure the document contains readable text (not scanned/image-only)."
                        ),
                        "step": "extraction",
                    },
                )

        # ── Pipeline execution ───────────────────────────────────────────────
        logger.info(
            "[REQUEST:%s] Starting CrewAI pipeline — journal=%s chars=%d",
            request_id, journal, len(paper_text),
        )
        start = time.time()

        result = run_pipeline(paper_text, journal)

        elapsed = round(time.time() - start, 1)
        docx_filename = result["docx_filename"]
        compliance_report = result["compliance_report"]
        overall_score = compliance_report.get("overall_score", "N/A")
        output_metadata = result.get("output_metadata", {})
        pipeline_metrics = result.get("pipeline_metrics", {})

        # Improvement 8: warn if pipeline exceeded expected runtime
        if elapsed > MAX_PIPELINE_RUNTIME:
            logger.warning(
                "[REQUEST:%s] Pipeline runtime exceeded limit — %.1fs > %ds",
                request_id, elapsed, MAX_PIPELINE_RUNTIME,
            )

        logger.info(
            "[REQUEST:%s] Pipeline complete — score=%s docx=%s size=%sKB total=%.1fs",
            request_id, overall_score, docx_filename,
            output_metadata.get("size_kb", "?"), elapsed,
        )

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "request_id": request_id,
                "download_url": f"/download/{docx_filename}",
                "compliance_report": compliance_report,
                "changes_made": compliance_report.get("changes_made", []),
                "processing_time_seconds": elapsed,
                "output_metadata": output_metadata,
                "pipeline_metrics": pipeline_metrics,
            },
        )

    except HTTPException:
        raise  # Re-raise validation errors as-is

    except RuleLoadError as e:
        logger.warning("[REQUEST:%s] Rule load error: %s", request_id, e)
        raise HTTPException(
            status_code=422,
            detail={
                "success": False,
                "error": str(e),
                "supported_journals": get_supported_journals(),
                "step": "interpret",
            },
        )

    except ParseError as e:
        logger.warning("[REQUEST:%s] Parse error: %s", request_id, e)
        raise HTTPException(
            status_code=422,
            detail={"success": False, "error": str(e), "step": "parse"},
        )

    except TransformError as e:
        logger.warning("[REQUEST:%s] Transform error: %s", request_id, e)
        raise HTTPException(
            status_code=422,
            detail={"success": False, "error": str(e), "step": "transform"},
        )

    except ValidationError as e:
        logger.warning("[REQUEST:%s] Validation error: %s", request_id, e)
        raise HTTPException(
            status_code=422,
            detail={"success": False, "error": str(e), "step": "validate"},
        )

    except LLMResponseError as e:
        logger.error("[REQUEST:%s] LLM response error: %s", request_id, e)
        raise HTTPException(
            status_code=422,
            detail={
                "success": False,
                "error": "The AI model returned an unexpected response. Please try again.",
                "step": "llm",
            },
        )

    except DocumentWriteError as e:
        logger.error("[REQUEST:%s] DOCX write error: %s", request_id, e)
        raise HTTPException(
            status_code=500,
            detail={"success": False, "error": str(e), "step": "docx_writer"},
        )

    except ToolError as e:
        # Catch-all for any other ToolError subclasses
        logger.error("[REQUEST:%s] Tool error: %s", request_id, e)
        raise HTTPException(
            status_code=422,
            detail={"success": False, "error": str(e), "step": "pipeline"},
        )

    except Exception as e:
        logger.exception("[REQUEST:%s] Unexpected pipeline error: %s", request_id, e)
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": "An unexpected pipeline error occurred. Please try again.",
                "step": "pipeline",
            },
        )

    finally:
        if upload_path.exists():
            upload_path.unlink(missing_ok=True)
            logger.debug("[REQUEST:%s] Temp upload file cleaned up", request_id)


# ---------------------------------------------------------------------------
# GET /download/{filename}
# ---------------------------------------------------------------------------
@app.get("/download/{filename}")
async def download_file(filename: str) -> FileResponse:
    """
    Download the formatted DOCX file.

    Security:
      - Regex validates filename (alphanumeric, hyphens, underscores, dots only)
      - Only serves .docx files
      - Path resolved and verified to be inside outputs/ directory
    """
    # Allow only safe characters — prevents path traversal and injection
    if not re.match(r"^[a-zA-Z0-9_\-\.]+$", filename):
        raise HTTPException(
            status_code=400,
            detail={"success": False, "error": "Invalid filename format."},
        )

    # Only serve .docx files
    if not filename.endswith(".docx"):
        raise HTTPException(
            status_code=400,
            detail={"success": False, "error": "Only .docx files can be downloaded."},
        )

    # Resolve and confirm the path stays inside OUTPUTS_DIR
    file_path = (OUTPUTS_DIR / filename).resolve()
    if not str(file_path).startswith(str(OUTPUTS_DIR.resolve())):
        raise HTTPException(
            status_code=403,
            detail={"success": False, "error": "Access denied."},
        )

    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail={
                "success": False,
                "error": f"File '{filename}' not found or has already been deleted.",
            },
        )

    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
