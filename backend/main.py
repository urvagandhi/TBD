import logging
import os
import time
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

load_dotenv(override=True)

# ---------------------------------------------------------------------------
# Logging — configure once at process start
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

from crew import run_pipeline
from tools.pdf_reader import extract_pdf_text
from tools.docx_reader import extract_docx_text
from tools.rule_loader import JOURNAL_MAP, get_supported_journals

app = FastAPI(
    title="Agent Paperpal API",
    description="Autonomous manuscript formatting system — HackaMined 2026",
    version="1.0.0",
)

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

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
MIN_TEXT_LENGTH = 100
ALLOWED_EXTENSIONS = {"pdf", "docx"}


def _get_extension(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _sanitize_filename(filename: str) -> str:
    """Prevent path traversal: reject any filename with directory separators."""
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    return filename


@app.get("/health")
async def health():
    logger.info("[HEALTH] GET /health — service ok")
    return {"status": "ok", "service": "Agent Paperpal"}


@app.post("/format")
async def format_document(
    file: UploadFile = File(...),
    journal: str = Form(...),
):
    """
    Upload a PDF or DOCX and format it according to the selected journal style.

    Validation order:
    1. File extension (pdf/docx)
    2. Journal name (must be in JOURNAL_MAP)
    3. File size (≤ 10MB)
    4. Extracted text length (≥ 100 chars)
    """
    request_id = uuid.uuid4().hex[:8]
    ext = _get_extension(file.filename or "")

    logger.info(
        "[REQUEST:%s] POST /format — file=%s journal=%s",
        request_id, file.filename, journal,
    )

    if ext not in ALLOWED_EXTENSIONS:
        logger.warning("[REQUEST:%s] Rejected — unsupported extension '.%s'", request_id, ext)
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type '.{ext}'. Upload a PDF or DOCX.",
        )

    if journal.lower().strip() not in JOURNAL_MAP:
        logger.warning("[REQUEST:%s] Rejected — unknown journal '%s'", request_id, journal)
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported journal '{journal}'. Choose from: {get_supported_journals()}",
        )

    content = await file.read()
    size_kb = round(len(content) / 1024, 1)

    if len(content) > MAX_FILE_SIZE:
        logger.warning("[REQUEST:%s] Rejected — file too large (%sKB)", request_id, size_kb)
        raise HTTPException(
            status_code=413,
            detail="File exceeds 10MB limit.",
        )

    logger.info("[REQUEST:%s] File accepted — size=%sKB type=%s", request_id, size_kb, ext.upper())

    upload_filename = f"{uuid.uuid4().hex}_{file.filename}"
    upload_path = UPLOADS_DIR / upload_filename

    try:
        upload_path.write_bytes(content)

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

        if len(paper_text.strip()) < MIN_TEXT_LENGTH:
            logger.warning("[REQUEST:%s] Rejected — extracted text too short (%d chars)", request_id, len(paper_text.strip()))
            raise HTTPException(
                status_code=422,
                detail="Extracted text is too short. Ensure the document contains readable text.",
            )

        logger.info("[REQUEST:%s] Starting CrewAI pipeline — journal=%s", request_id, journal)
        start = time.time()
        result = run_pipeline(paper_text, journal)
        elapsed = round(time.time() - start, 1)

        docx_filename = result["docx_filename"]
        compliance_report = result["compliance_report"]
        overall_score = compliance_report.get("overall_score", "N/A")

        logger.info(
            "[REQUEST:%s] Pipeline complete — score=%s docx=%s total=%.1fs",
            request_id, overall_score, docx_filename, elapsed,
        )

        return {
            "success": True,
            "download_url": f"/download/{docx_filename}",
            "compliance_report": compliance_report,
            "processing_time_seconds": elapsed,
        }

    except HTTPException:
        raise
    except ValueError as e:
        logger.error("[REQUEST:%s] Validation error — %s", request_id, str(e))
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        logger.exception("[REQUEST:%s] Pipeline error — %s", request_id, str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Pipeline error: {str(e)}",
        ) from e
    finally:
        if upload_path.exists():
            upload_path.unlink(missing_ok=True)
            logger.debug("[REQUEST:%s] Temp upload file cleaned up", request_id)


@app.get("/download/{filename}")
async def download_file(filename: str):
    """
    Download the formatted DOCX file.

    Security: rejects any filename containing path traversal characters (../ etc).
    """
    _sanitize_filename(filename)
    file_path = OUTPUTS_DIR / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found or already deleted.")

    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
