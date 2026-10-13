"""
Dynamic Journal Discovery Module.

Searches the web for any journal's author guidelines, fetches the content,
and extracts structured formatting rules using Gemini LLM. Results are
cached in backend/rules/extracted/ for instant reuse.
"""
import json
import os
import re
import hashlib
import httpx
from pathlib import Path
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from urllib.parse import urljoin, urlparse

from tools.logger import get_logger

_backend_dir = Path(__file__).resolve().parent.parent
load_dotenv(_backend_dir / ".env")
logger = get_logger(__name__)

RULES_DIR = Path(__file__).resolve().parent.parent / "rules"
EXTRACTED_DIR = RULES_DIR / "extracted"
EXTRACTED_DIR.mkdir(exist_ok=True)

_NOISE_TAGS = ["script", "style", "nav", "footer", "header", "aside", "iframe"]
_MAX_FETCH_CHARS = 20_000

_GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[:60]


def _cache_path(journal_name: str) -> Path:
    return EXTRACTED_DIR / f"{_slugify(journal_name)}.json"


def _read_cache(journal_name: str) -> dict | None:
    path = _cache_path(journal_name)
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "style_name" in data:
                logger.info("[DISCOVERY] Cache hit for '%s'", journal_name)
                return data
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
    return None


def _write_cache(journal_name: str, rules: dict) -> Path:
    path = _cache_path(journal_name)
    path.write_text(json.dumps(rules, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("[DISCOVERY] Cached rules for '%s' → %s", journal_name, path.name)
    return path


# ---------------------------------------------------------------------------
# Step 1: Search the web
# ---------------------------------------------------------------------------

def search_journal(query: str, max_results: int = 5, focus: str = "") -> list[dict]:
    """
    Search DuckDuckGo for a journal's author guidelines page.

    Returns a list of dicts: [{title, url, snippet}]
    """
    try:
        from ddgs import DDGS

        search_query = f"{query} {focus} author guidelines formatting".strip()
        logger.info("[DISCOVERY] Searching: %s", search_query)

        results = list(DDGS().text(search_query, max_results=max_results))

        filtered = []
        for r in results:
            url = r.get("href", r.get("link", ""))
            title = r.get("title", "")
            snippet = r.get("body", r.get("snippet", ""))
            if url and title:
                filtered.append({"title": title, "url": url, "snippet": snippet})

        logger.info("[DISCOVERY] Found %d results", len(filtered))
        return filtered

    except ImportError:
        logger.warning("[DISCOVERY] duckduckgo_search not installed")
        return []
    except Exception as e:
        logger.warning("[DISCOVERY] Search failed: %s", e)
        return []


def extract_guideline_links(page_text: str, base_url: str, max_links: int = 8) -> list[dict]:
    """Return relevant, same-site guideline links from fetched Markdown/text.

    Discovery is intentionally bounded: it follows one link level and only
    links whose visible text or URL looks related to manuscript requirements.
    """
    base_host = urlparse(base_url).netloc.lower().removeprefix("www.")
    pattern = re.compile(r"\[([^\]]{2,160})\]\((https?://[^)\s]+|/[^)\s]+)\)")
    relevant = re.compile(r"author|submit|manuscript|guideline|instruction|reference|citation|format|template|prepare", re.I)
    links, seen = [], {base_url}
    for label, raw_url in pattern.findall(page_text):
        url = urljoin(base_url, raw_url)
        parsed = urlparse(url)
        host = parsed.netloc.lower().removeprefix("www.")
        if host != base_host or url in seen or not relevant.search(f"{label} {url}"):
            continue
        seen.add(url)
        links.append({"title": label.strip(), "url": url, "snippet": "Linked from the selected official guidance page."})
        if len(links) >= max_links:
            break
    return links


# ---------------------------------------------------------------------------
# Step 2: Fetch and clean page content
# ---------------------------------------------------------------------------

def fetch_journal_page(url: str) -> str:
    """
    Fetch a URL and return cleaned plain text suitable for LLM analysis.
    Uses Jina Reader as primary (clean markdown, bypasses bot detection).
    Falls back to direct httpx if Jina fails.
    Returns empty string on failure.
    """
    # --- Primary: Jina Reader ---
    try:
        logger.info("[DISCOVERY] Fetching via Jina Reader: %s", url)
        jina_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "text/plain",
        }
        resp = httpx.get(f"https://r.jina.ai/{url}", headers=jina_headers, timeout=30, follow_redirects=True)
        resp.raise_for_status()

        text = resp.text
        text = re.sub(r"\n{3,}", "\n\n", text)

        truncated = len(text) > _MAX_FETCH_CHARS
        result = text[:_MAX_FETCH_CHARS]
        if truncated:
            result += f"\n\n[... TRUNCATED at {_MAX_FETCH_CHARS} chars ...]"

        logger.info("[DISCOVERY] Jina fetched %d chars (truncated=%s)", len(result), truncated)
        return result

    except Exception as e:
        logger.warning("[DISCOVERY] Jina failed for %s: %s — falling back to direct fetch", url, e)

    # --- Fallback: direct httpx + BeautifulSoup ---
    try:
        logger.info("[DISCOVERY] Fetching via direct httpx: %s", url)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        resp = httpx.get(url, headers=headers, timeout=20, follow_redirects=True)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(_NOISE_TAGS):
            tag.decompose()

        text = soup.get_text(separator="\n", strip=True)
        text = re.sub(r"\n{3,}", "\n\n", text)

        truncated = len(text) > _MAX_FETCH_CHARS
        result = text[:_MAX_FETCH_CHARS]
        if truncated:
            result += f"\n\n[... TRUNCATED at {_MAX_FETCH_CHARS} chars ...]"

        logger.info("[DISCOVERY] Direct fetch got %d chars (truncated=%s)", len(result), truncated)
        return result

    except Exception as e2:
        logger.warning("[DISCOVERY] Direct fetch also failed for %s: %s", url, e2)
        return ""


# ---------------------------------------------------------------------------
# Step 3: Extract structured rules via Gemini
# ---------------------------------------------------------------------------

_EXTRACTION_PROMPT = """You are an expert academic formatting analyst. Given the text of a journal's author guidelines document, extract the formatting rules into a structured JSON object.

You MUST return ONLY a valid JSON object with EXACTLY these top-level keys and sub-keys:

1. style_name (string): Name of the formatting style

2. document (object):
   - font (string, e.g. "Times New Roman")
   - font_size (integer, e.g. 12)
   - line_spacing (float, e.g. 2.0)
   - margins (object): top, bottom, left, right — each a string like "1in"
   - alignment (string): "left" | "justify" | "center" | "right"
   - columns (integer, 1 or 2)

3. title_page (object):
   - title_case (string): "Title Case" | "UPPERCASE" | "Sentence case"
   - title_bold (boolean)
   - title_centered (boolean)
   - title_font_size (integer)

4. abstract (object):
   - label (string, e.g. "Abstract")
   - label_bold (boolean)
   - label_centered (boolean)
   - label_italic (boolean)
   - max_words (integer, e.g. 250)
   - indent_first_line (boolean)
   - keywords_present (boolean)
   - keywords_label (string, e.g. "Keywords:")
   - keywords_italic (boolean)

5. headings (object): H1, H2, H3 — each with:
   - bold (boolean)
   - italic (boolean)
   - centered (boolean)
   - underline (boolean)
   - case (string): "Title Case" | "UPPERCASE" | "Sentence case"
   - numbering (string): "none" | "numeric" | "roman" | "alpha"
   - font_size (integer)

6. citations (object):
   - style (string): "author-date" | "numbered"
   - brackets (string): "parentheses" | "square" | "none"
   - format_one_author (string, e.g. "(Author Year)")
   - format_two_authors (string, e.g. "(Author & Author Year)")
   - format_three_plus (string, e.g. "(Author et al. Year)")
   - format_numbered (string or null, e.g. "[N]")
   - include_page_for_quotes (boolean)
   - page_format (string, e.g. "p. 45")

7. references (object):
   - section_label (string, e.g. "References")
   - label_bold (boolean)
   - label_centered (boolean)
   - label_italic (boolean)
   - ordering (string): "alphabetical" | "appearance"
   - hanging_indent (boolean)
   - indent_size (string, e.g. "0.5in")
   - line_spacing (float, e.g. 2.0)
   - space_between_entries (boolean)
   - formats (object): journal_article, book, book_chapter, website, conference_paper — each a string template

8. figures (object):
   - label_prefix (string, e.g. "Figure" or "Fig.")
   - label_bold (boolean)
   - label_italic (boolean)
   - caption_position (string): "above" | "below"
   - caption_italic (boolean)
   - caption_alignment (string): "left" | "center" | "right"
   - numbering (string): "arabic" | "roman"
   - note_label (string, e.g. "Note:")

9. tables (object):
   - label_prefix (string, e.g. "Table")
   - label_bold (boolean)
   - label_italic (boolean)
   - caption_position (string): "above" | "below"
   - caption_italic (boolean)
   - caption_alignment (string): "left" | "center" | "right"
   - numbering (string): "arabic" | "roman"
   - border_style (string): "full" | "full_grid" | "top_bottom_only" | "header_only" | "none"
   - note_label (string, e.g. "Note:")

10. equations (object):
    - numbering (string, e.g. "right_aligned")
    - numbering_format (string, e.g. "(1)")

11. general_rules (object):
    - doi_format (string)
    - url_format (string)
    - date_format (string)
    - et_al_threshold (integer)
    - use_ampersand_in_citations (boolean)
    - use_ampersand_in_references (boolean)
    - oxford_comma (boolean)

IMPORTANT RULES:
- You MUST include ALL sub-keys listed above in your output
- If a specific rule is not mentioned in the guidelines, use sensible academic defaults
- font_size must be an integer (e.g., 12)
- line_spacing must be a float (e.g., 2.0)
- margins should be strings like "1in"
- Return ONLY the JSON object, no markdown fences, no explanation
"""


def _call_gemini(prompt: str, text: str) -> str:
    """Call Gemini API and return the raw response text."""
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{_GEMINI_MODEL}:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt + "\n\n" + text}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 8192},
    }
    try:
        resp = httpx.post(url, json=payload, timeout=120)
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (401, 403):
            raise RuntimeError(
                "Gemini access was denied. Configure an active GEMINI_API_KEY "
                "with access to the Generative Language API, then restart the backend."
            ) from None
        raise RuntimeError(
            f"Gemini rule extraction failed with HTTP {exc.response.status_code}."
        ) from None
    except httpx.RequestError as exc:
        raise RuntimeError("Could not reach Gemini for journal-rule extraction.") from None
    data = resp.json()

    candidates = data.get("candidates", [])
    if not candidates:
        raise RuntimeError("No candidates in Gemini response")

    parts = candidates[0].get("content", {}).get("parts", [])
    return "".join(p.get("text", "") for p in parts)


def extract_rules_from_text(text: str, journal_name: str) -> dict:
    """
    Send guideline text to Gemini and parse the structured JSON rules.
    Raises on failure so the caller can handle it.
    """
    logger.info("[DISCOVERY] Extracting rules for '%s' (%d chars)", journal_name, len(text))
    raw = _call_gemini(_EXTRACTION_PROMPT, text)

    json_match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not json_match:
        raise RuntimeError("Gemini did not return JSON")

    rules = json.loads(json_match.group())
    required_keys = [
        "style_name", "document", "title_page", "abstract",
        "headings", "citations", "references", "figures", "tables", "general_rules",
    ]
    missing = [k for k in required_keys if k not in rules]
    if missing:
        raise RuntimeError(f"Extracted rules missing keys: {missing}")

    rules = _fill_defaults(rules)

    return rules


def _fill_defaults(rules: dict) -> dict:
    """Replace any None/null values with sensible academic defaults."""
    defaults = {
        "equations": {
            "numbering": "right_aligned",
            "numbering_format": "(1)",
        },
        "title_page": {
            "title_case": "Title Case",
            "title_bold": True,
            "title_centered": True,
            "title_font_size": 14,
        },
        "abstract": {
            "label": "Abstract",
            "label_bold": True,
            "label_centered": False,
            "label_italic": False,
            "max_words": 250,
            "indent_first_line": False,
            "keywords_present": True,
            "keywords_label": "Keywords:",
            "keywords_italic": False,
        },
        "headings": {
            "H1": {"bold": True, "italic": False, "centered": False, "underline": False, "case": "Title Case", "numbering": "none", "font_size": 14},
            "H2": {"bold": True, "italic": False, "centered": False, "underline": False, "case": "Title Case", "numbering": "numeric", "font_size": 12},
            "H3": {"bold": True, "italic": True, "centered": False, "underline": False, "case": "Sentence case", "numbering": "none", "font_size": 12},
        },
        "citations": {
            "style": "author-date",
            "brackets": "parentheses",
            "format_one_author": "(Author Year)",
            "format_two_authors": "(Author & Author Year)",
            "format_three_plus": "(Author et al. Year)",
            "format_numbered": None,
            "include_page_for_quotes": False,
            "page_format": "p. 45",
        },
        "references": {
            "section_label": "References",
            "label_bold": True,
            "label_centered": False,
            "label_italic": False,
            "ordering": "alphabetical",
            "hanging_indent": True,
            "indent_size": "0.5in",
            "line_spacing": 2.0,
            "space_between_entries": True,
        },
        "figures": {
            "label_prefix": "Figure",
            "label_bold": True,
            "label_italic": False,
            "caption_position": "below",
            "caption_italic": True,
            "caption_alignment": "left",
            "numbering": "arabic",
            "note_label": "Note:",
        },
        "tables": {
            "label_prefix": "Table",
            "label_bold": True,
            "label_italic": False,
            "caption_position": "above",
            "caption_italic": True,
            "caption_alignment": "left",
            "numbering": "arabic",
            "border_style": "full",
            "note_label": "Note:",
        },
        "general_rules": {
            "doi_format": "doi:10.xxxx/xxxxx",
            "url_format": "URL",
            "date_format": "YYYY-MM-DD",
            "et_al_threshold": 3,
            "use_ampersand_in_citations": False,
            "use_ampersand_in_references": False,
            "oxford_comma": True,
        },
    }

    def _merge(defaults_obj, target):
        if not isinstance(defaults_obj, dict) or not isinstance(target, dict):
            return target
        for key, default_val in defaults_obj.items():
            if key not in target:
                target[key] = default_val
            elif isinstance(default_val, dict) and isinstance(target[key], dict):
                _merge(default_val, target[key])
            elif target[key] is None:
                target[key] = default_val
        return target

    for section, section_defaults in defaults.items():
        if section not in rules:
            rules[section] = section_defaults
        elif isinstance(rules[section], dict):
            _merge(section_defaults, rules[section])

    return rules


# ---------------------------------------------------------------------------
# Orchestrator: search → fetch → extract → cache
# ---------------------------------------------------------------------------

def discover_journal(journal_name: str, url: str | None = None) -> dict:
    """
    Full discovery pipeline for an unknown journal.

    1. Check cache
    2. If url provided, fetch directly; otherwise search DuckDuckGo
    3. Fetch page content
    4. Extract rules via Gemini
    5. Cache and return

    Returns the rules dict. Raises on any step failure.
    """
    cached = _read_cache(journal_name)
    if cached:
        return cached

    if not url:
        results = search_journal(journal_name)
        if not results:
            raise RuntimeError(f"No search results found for '{journal_name}'")
        url = results[0]["url"]
        logger.info("[DISCOVERY] Using top result: %s", url)

    page_text = fetch_journal_page(url)
    if not page_text or len(page_text) < 200:
        raise RuntimeError(f"Could not fetch meaningful content from {url}")

    rules = extract_rules_from_text(page_text, journal_name)
    rules["style_name"] = journal_name
    _write_cache(journal_name, rules)

    return rules


def list_extracted_journals() -> list[dict]:
    """Return metadata for all cached/extracted journals."""
    journals = []
    for path in sorted(EXTRACTED_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            journals.append({
                "slug": path.stem,
                "style_name": data.get("style_name", path.stem),
                "file": path.name,
            })
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
    return journals
