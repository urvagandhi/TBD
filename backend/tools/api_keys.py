"""
Round-robin API key rotation with fallback.

Keys are read from environment variables at import time:
  GEMINI_API_KEYS  — comma-separated list of round-robin keys
  GEMINI_FALLBACK_KEY — used only when the RR key fails (429/5xx)

Usage:
    from tools.api_keys import get_next_key, get_fallback_key, key_count
"""
import os
import threading

from tools.logger import get_logger

logger = get_logger(__name__)

_rr_keys: list[str] = []
_fallback_key: str = ""
_index = 0
_lock = threading.Lock()


def _load_keys() -> None:
    global _rr_keys, _fallback_key
    raw = os.getenv("GEMINI_API_KEYS", "")
    _rr_keys = [k.strip() for k in raw.split(",") if k.strip()]

    _fallback_key = os.getenv("GEMINI_FALLBACK_KEY", "").strip()

    # Fallback: if no RR keys configured, use legacy single-key env var
    if not _rr_keys:
        legacy = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
        if legacy:
            _rr_keys = [legacy]


_load_keys()


def get_next_key() -> str:
    """Return the next API key in round-robin order."""
    global _index
    if not _rr_keys:
        raise RuntimeError("No Gemini API keys configured (GEMINI_API_KEYS is empty).")
    with _lock:
        key = _rr_keys[_index % len(_rr_keys)]
        _index += 1
    return key


def get_fallback_key() -> str:
    """Return the fallback key, or empty string if not configured."""
    return _fallback_key


def key_count() -> int:
    """Number of round-robin keys available."""
    return len(_rr_keys)


def has_fallback() -> bool:
    """Whether a fallback key is configured."""
    return bool(_fallback_key)


def startup_summary() -> str:
    """Human-readable summary for startup logs."""
    parts = [f"{len(_rr_keys)} RR key(s) loaded"]
    if _fallback_key:
        parts.append("fallback key: set")
    else:
        parts.append("fallback key: not set")
    return " | ".join(parts)
