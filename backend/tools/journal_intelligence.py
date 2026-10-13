"""Evidence-backed discovery, review, and approval for journal rule sets."""
from __future__ import annotations

import copy
import hashlib
import json
import re
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from tools.journal_discovery import extract_guideline_links, extract_rules_from_text, fetch_journal_page, search_journal
from tools.logger import get_logger
from tools.rule_instruction_compiler import compile_rule_instructions

logger = get_logger(__name__)

RULES_DIR = Path(__file__).resolve().parent.parent / "rules"
DRAFTS_DIR = RULES_DIR / "discovery_drafts"
APPROVED_DIR = RULES_DIR / "approved"
for _directory in (DRAFTS_DIR, APPROVED_DIR):
    _directory.mkdir(exist_ok=True)

DRAFT_TTL_SECONDS = 60 * 60
_OFFICIAL_HINTS = (
    "nature.com", "springer.com", "elsevier.com", "wiley.com", "tandfonline.com",
    "sagepub.com", "oup.com", "academic.oup.com", "cambridge.org", "plos.org",
    "bmj.com", "nejm.org", "thelancet.com", "jamanetwork.com", "ieee.org",
    "acm.org", "aps.org", "cell.com", "sciencedirect.com", "frontiersin.org", "peerj.com",
)
_CRITICAL_CATEGORIES = {
    "document": ("document",),
    "abstract": ("abstract",),
    "headings": ("headings",),
    "references": ("citations", "references"),
}
_FOLLOW_UP_TOPICS = {
    "document": "manuscript preparation font margins layout",
    "abstract": "abstract word limit keywords",
    "headings": "manuscript section headings structure",
    "references": "reference citation style bibliography",
}
_PATH_KEYWORDS = {
    "document.font": ("font", "typeface"),
    "document.font_size": ("font size", "point", " pt"),
    "document.line_spacing": ("line spacing", "double-spaced", "single-spaced", "spacing"),
    "document.margins": ("margin",),
    "document.columns": ("column",),
    "abstract": ("abstract", "word limit", "words"),
    "headings": ("heading", "section", "subheading"),
    "citations": ("citation", "cite", "reference"),
    "references": ("reference", "bibliography", "vancouver", "doi"),
    "figures": ("figure", "caption"),
    "tables": ("table", "caption"),
}
_ENUMS = {
    "document.alignment": {"left", "justify", "center", "right"},
    "citations.style": {"author-date", "numbered", "footnote"},
    "citations.brackets": {"parentheses", "square", "none"},
    "references.ordering": {"alphabetical", "appearance"},
    "figures.caption_position": {"above", "below"},
    "tables.caption_position": {"above", "below"},
    "tables.border_style": {"full", "full_grid", "top_bottom_only", "header_only", "none"},
}


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:60]


def _source_score(source: dict[str, str], journal_name: str) -> tuple[int, list[str]]:
    url = source.get("url", "")
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    title = source.get("title", "").lower()
    text = f"{title} {source.get('snippet', '')}".lower()
    score, reasons = 0, []
    recognized_domain = any(host == hint or host.endswith(f".{hint}") for hint in _OFFICIAL_HINTS)
    requested_in_title = journal_name.lower() in title
    guidance_in_title = any(word in title for word in ("author", "submission", "instruction", "guideline", "manuscript"))
    if recognized_domain:
        score += 70
        reasons.append("Recognized publisher or journal domain")
    if guidance_in_title:
        score += 20
        reasons.append("Page title identifies author or manuscript guidance")
    elif any(word in text for word in ("author", "submission", "instruction", "guideline", "manuscript")):
        score += 8
        reasons.append("Search snippet mentions author or submission guidance")
    if requested_in_title:
        score += 10
        reasons.append("Page title names the requested journal")
    elif journal_name.lower() in text:
        score += 4
        reasons.append("Search snippet names the requested journal")
    if parsed.scheme == "https":
        score += 5
        reasons.append("Uses HTTPS")
    if any(noisy in host for noisy in ("facebook.", "linkedin.", "researchgate.", "impactfactor")):
        score -= 80
        reasons.append("Third-party or social source penalty")
    # A publisher domain is not enough.  Generic publisher pages and pages for
    # another journal must never become a high-confidence source for this one.
    if not (recognized_domain and requested_in_title and guidance_in_title):
        score = min(score, 89)
        if recognized_domain and not requested_in_title:
            reasons.append("Not a high-confidence match: page title does not name the requested journal")
    return score, reasons


def rank_sources(journal_name: str, sources: list[dict[str, str]]) -> list[dict[str, Any]]:
    ranked, seen = [], set()
    for source in sources:
        url = source.get("url", "")
        if not url or url in seen:
            continue
        seen.add(url)
        score, reasons = _source_score(source, journal_name)
        ranked.append({
            "id": hashlib.sha256(url.encode()).hexdigest()[:12],
            "title": source.get("title", url),
            "url": url,
            "snippet": source.get("snippet", "")[:300],
            "score": score,
            "official_likelihood": "high" if score >= 90 else "medium" if score >= 35 else "low",
            "trust_reasons": reasons,
        })
    return sorted(ranked, key=lambda item: item["score"], reverse=True)


def _validate_rules(rules: dict) -> list[str]:
    required = {"style_name", "document", "abstract", "headings", "citations", "references", "figures", "tables", "general_rules"}
    missing = sorted(required - set(rules)) if isinstance(rules, dict) else sorted(required)
    errors = [f"Missing required section: {key}" for key in missing]
    if not isinstance(rules, dict):
        return errors
    try:
        from tools.rule_loader import _get_schema
        import jsonschema
        schema = _get_schema()
        if schema:
            jsonschema.validate(instance=rules, schema=schema)
    except Exception as exc:
        errors.append(f"Schema validation failed: {str(exc)[:220]}")
    return errors


def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, child in value.items():
            result.update(_flatten(child, f"{prefix}.{key}" if prefix else key))
        return result
    return {prefix: value}


def _keywords_for(path: str) -> tuple[str, ...]:
    for prefix, keywords in _PATH_KEYWORDS.items():
        if path == prefix or path.startswith(prefix + "."):
            return keywords
    return tuple(path.split(".")[-1].replace("_", " ").split())


def _field_facts(rules: dict, evidence_sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    facts = []
    for path, value in _flatten(rules).items():
        if path == "style_name":
            continue
        keywords = _keywords_for(path)
        match = next((
            (source, line)
            for source in evidence_sources
            for line in source["text"].splitlines()
            if line.strip() and any(word.lower() in line.lower() for word in keywords)
        ), None)
        source, excerpt = match if match else (None, None)
        facts.append({
            "path": path,
            "value": value,
            "provenance": "source" if excerpt else "default",
            "validation": "evidenced" if excerpt else "not_stated_by_source",
            "source_url": source["url"] if excerpt else None,
            "excerpt": excerpt[:400] if excerpt else None,
        })
    return facts


def _quality(source: dict[str, Any], facts: list[dict[str, Any]], validation_errors: list[str], compilation: dict) -> dict[str, Any]:
    critical = {}
    blockers = []
    for category, prefixes in _CRITICAL_CATEGORIES.items():
        evidenced = any(
            fact["provenance"] == "source" and any(fact["path"] == prefix or fact["path"].startswith(prefix + ".") for prefix in prefixes)
            for fact in facts
        )
        critical[category] = evidenced
        if not evidenced:
            blockers.append(f"Add source evidence for {category} requirements.")
    if source.get("official_likelihood") != "high":
        blockers.insert(0, "Select a high-trust official journal or publisher source.")
    if validation_errors:
        blockers.extend(validation_errors)
    source_count = sum(1 for fact in facts if fact["provenance"] == "source")
    coverage = round(100 * source_count / len(facts)) if facts else 0
    return {
        "source_trust": source.get("official_likelihood", "low"),
        "source_score": source.get("score", 0),
        "schema_valid": not validation_errors,
        "critical_categories": critical,
        "critical_coverage": round(100 * sum(critical.values()) / len(critical)),
        "field_evidence_coverage": coverage,
        "approval_blockers": blockers,
        "can_approve": not blockers,
        "unsupported_rule_count": len(compilation["unsupported_rules"]),
    }


def _draft_path(draft_id: str) -> Path:
    return DRAFTS_DIR / f"{draft_id}.json"


def _save_draft(draft: dict) -> None:
    _draft_path(draft["draft_id"]).write_text(json.dumps(draft, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_draft(draft_id: str) -> dict:
    path = _draft_path(draft_id)
    if not path.exists():
        raise ValueError("Journal discovery draft was not found or has expired.")
    draft = json.loads(path.read_text(encoding="utf-8"))
    if time.time() - draft.get("created_at", 0) > DRAFT_TTL_SECONDS:
        path.unlink(missing_ok=True)
        raise ValueError("Journal discovery draft expired. Search again to refresh the evidence.")
    return draft


def _refresh_draft(draft: dict) -> dict:
    compilation = compile_rule_instructions(draft["rules"])
    draft["compilation"] = compilation
    draft["quality"] = _quality(draft["selected_source"], draft["field_facts"], draft["validation_errors"], compilation)
    draft["verification_coverage"] = draft["quality"]["field_evidence_coverage"]
    draft["status"] = "ready_for_approval" if draft["quality"]["can_approve"] else "needs_review"
    return draft


def _merge_candidates(*candidate_lists: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged, seen = [], set()
    for candidates in candidate_lists:
        for candidate in candidates:
            if candidate["url"] not in seen:
                seen.add(candidate["url"])
                merged.append(candidate)
    return sorted(merged, key=lambda item: item["score"], reverse=True)


def _collect_evidence_sources(journal_name: str, seed: dict[str, Any], candidates: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Fetch a bounded set of relevant official pages and one level of links."""
    evidence, seen = [], set()

    def add(source: dict[str, Any]) -> None:
        if source["url"] in seen or len(evidence) >= 6:
            return
        text = fetch_journal_page(source["url"])
        if len(text.strip()) >= 200:
            seen.add(source["url"])
            evidence.append({**source, "text": text[:20_000]})

    add(seed)
    for candidate in candidates:
        if candidate["url"] != seed["url"] and candidate["official_likelihood"] == "high":
            add(candidate)
    if evidence:
        linked_raw = extract_guideline_links(evidence[0]["text"], seed["url"])
        linked = rank_sources(journal_name, linked_raw)
        for candidate in linked:
            if candidate["official_likelihood"] != "low":
                add(candidate)
        candidates = _merge_candidates(candidates, linked)
    return evidence, candidates


def discover_journal(journal_name: str) -> dict:
    query = journal_name.strip()
    if len(query) < 2:
        raise ValueError("Journal name must contain at least two characters.")
    primary = rank_sources(query, search_journal(query, max_results=8))
    focused = [rank_sources(query, search_journal(query, max_results=5, focus=focus)) for focus in _FOLLOW_UP_TOPICS.values()]
    candidates = _merge_candidates(primary, *focused)
    if not candidates:
        raise ValueError("No journal guideline sources were found.")
    return analyze_source(query, candidates, candidates[0]["id"])


def analyze_source(journal_name: str, candidates: list[dict[str, Any]], source_id: str) -> dict:
    source = next((item for item in candidates if item["id"] == source_id), None)
    if not source:
        raise ValueError("Selected source is not part of this discovery result.")
    if source["official_likelihood"] == "low":
        raise ValueError("That source is not credible enough for automatic rule extraction. Choose an official guideline page or upload a guideline document.")
    evidence_sources, candidates = _collect_evidence_sources(journal_name, source, candidates)
    if not evidence_sources:
        raise ValueError("The selected source did not provide enough readable guideline text.")
    corpus = "\n\n".join(f"SOURCE: {item['url']}\n{item['text']}" for item in evidence_sources)
    rules = extract_rules_from_text(corpus, journal_name)
    rules["style_name"] = journal_name
    validation_errors = _validate_rules(rules)
    draft = {
        "draft_id": uuid.uuid4().hex,
        "created_at": time.time(),
        "journal_name": journal_name,
        "selected_source": source,
        "candidates": candidates,
        "rules": rules,
        "field_facts": _field_facts(rules, evidence_sources),
        "validation_errors": validation_errors,
        "edit_history": [],
        "discovery_summary": {
            "sources_inspected": [{"title": item["title"], "url": item["url"], "credibility": item["official_likelihood"]} for item in evidence_sources],
            "pages_inspected": len(evidence_sources),
            "search_strategy": "general author-guidance search plus targeted document, abstract, headings, and reference searches",
        },
    }
    _refresh_draft(draft)
    _save_draft(draft)
    return public_draft(draft)


def select_source(draft_id: str, source_id: str) -> dict:
    draft = _load_draft(draft_id)
    return analyze_source(draft["journal_name"], draft["candidates"], source_id)


def _set_path(target: dict, path: str, value: Any) -> None:
    keys = path.split(".")
    cursor = target
    for key in keys[:-1]:
        cursor = cursor[key]
    cursor[keys[-1]] = value


def _coerce_edit(path: str, old: Any, value: Any) -> Any:
    if path in _ENUMS and value not in _ENUMS[path]:
        raise ValueError(f"{path} must be one of: {', '.join(sorted(_ENUMS[path]))}.")
    if isinstance(old, bool):
        if not isinstance(value, bool):
            raise ValueError(f"{path} must be a boolean.")
    elif isinstance(old, int) and not isinstance(old, bool):
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"{path} must be an integer.")
    elif isinstance(old, float):
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError(f"{path} must be a number.")
        value = float(value)
    elif isinstance(old, str) and not isinstance(value, str):
        raise ValueError(f"{path} must be text.")
    return value


def update_draft_rules(draft_id: str, updates: list[dict[str, Any]]) -> dict:
    draft = _load_draft(draft_id)
    flattened = _flatten(draft["rules"])
    facts = {fact["path"]: fact for fact in draft["field_facts"]}
    if not isinstance(updates, list) or not updates:
        raise ValueError("Provide at least one rule update.")
    for update in updates:
        path, value = update.get("path"), update.get("value")
        if path not in flattened or path == "style_name":
            raise ValueError(f"{path!r} is not an editable rule field.")
        value = _coerce_edit(path, flattened[path], value)
        _set_path(draft["rules"], path, value)
        fact = facts[path]
        fact.update({"value": value, "provenance": "user_override", "validation": "reviewer_confirmed"})
        draft["edit_history"].append({"path": path, "value": value, "edited_at": time.time()})
    draft["field_facts"] = list(facts.values())
    draft["validation_errors"] = _validate_rules(draft["rules"])
    _refresh_draft(draft)
    _save_draft(draft)
    return public_draft(draft)


def public_draft(draft: dict) -> dict:
    return {
        "draft_id": draft["draft_id"], "journal_name": draft["journal_name"], "status": draft["status"],
        "selected_source": draft["selected_source"], "candidates": draft["candidates"], "rules": draft["rules"],
        "field_facts": draft["field_facts"], "quality": draft["quality"], "compilation": draft["compilation"],
        "verification_coverage": draft["verification_coverage"], "validation_errors": draft["validation_errors"],
        "edit_history": draft.get("edit_history", []), "discovery_summary": draft.get("discovery_summary", {}),
    }


def approve_draft(draft_id: str) -> dict:
    draft = _load_draft(draft_id)
    _refresh_draft(draft)
    if not draft["quality"]["can_approve"]:
        raise ValueError("This draft is not ready for approval: " + " ".join(draft["quality"]["approval_blockers"]))
    version = time.strftime("%Y%m%d-%H%M%S")
    slug = _slugify(draft["journal_name"])
    rule_set_id = f"{slug}:{version}"
    approved = copy.deepcopy(draft)
    approved.update({"rule_set_id": rule_set_id, "approved_at": time.time(), "status": "approved"})
    (APPROVED_DIR / f"{slug}--{version}.json").write_text(json.dumps(approved, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("[JOURNAL_INTELLIGENCE] Approved %s from %s", rule_set_id, draft["selected_source"]["url"])
    return {
        "rule_set_id": rule_set_id, "journal_name": draft["journal_name"], "rules": draft["rules"],
        "source": draft["selected_source"], "quality": draft["quality"], "compilation": draft["compilation"],
    }


def load_approved_rule_set(rule_set_id: str) -> dict:
    for path in APPROVED_DIR.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("rule_set_id") == rule_set_id:
                payload.setdefault("legacy", "field_facts" not in payload)
                return payload
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
    raise ValueError("Approved journal rule set was not found.")
