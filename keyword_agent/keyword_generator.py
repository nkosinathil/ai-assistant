"""Keyword generator: sends combined text to Ollama and parses the returned keywords."""

import json
import logging
import re
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "llama3"


KEYWORD_PROMPT_TEMPLATE = """You are a forensic investigator assistant.

Given the following text from allegations and supporting documents, extract a comprehensive keyword list for use in a digital forensic investigation.

Extract the following categories:
1. ENTITIES: Full names of people, organisations, companies, addresses, locations.
2. DATES_FINANCIALS: Specific dates, monetary amounts, account numbers, transaction references.
3. RED_FLAGS: Terms indicative of fraud, misconduct, or criminal activity (e.g. "bribe", "kickback", "falsified").
4. KEY_PHRASES: Domain-specific terms, technical jargon, product/project names, policy references.

Return ONLY a JSON object in this exact format (no markdown, no explanation):
{{
  "entities": ["keyword1", "keyword2"],
  "dates_financials": ["keyword1", "keyword2"],
  "red_flags": ["keyword1", "keyword2"],
  "key_phrases": ["keyword1", "keyword2"]
}}

TEXT TO ANALYSE:
{combined_text}
"""


def generate_keywords(
    combined_text: str,
    output_dir: Path,
    model: str = DEFAULT_MODEL,
    ollama_url: str = DEFAULT_OLLAMA_URL,
) -> dict:
    """Call Ollama to extract keywords from *combined_text*.

    Args:
        combined_text: All allegations + extracted text + OCR text concatenated.
        output_dir: The ``keywords/`` sub-directory of the case folder.
        model: Ollama model name to use.
        ollama_url: Base URL of the Ollama API server.

    Returns:
        A dict with ``keyword_list`` (list[str]) and ``keyword_metadata`` (list[dict]).
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    prompt = KEYWORD_PROMPT_TEMPLATE.format(combined_text=combined_text[:12000])
    raw_response = _call_ollama(prompt, model=model, ollama_url=ollama_url)
    categorised = _parse_response(raw_response)

    keyword_list = _flatten_and_deduplicate(categorised)
    keyword_metadata = _build_metadata(categorised)

    # Write keyword_list.txt
    kw_list_path = output_dir / "keyword_list.txt"
    kw_list_path.write_text("\n".join(keyword_list), encoding="utf-8")

    # Write keyword_metadata.json
    kw_meta_path = output_dir / "keyword_metadata.json"
    kw_meta_path.write_text(json.dumps(keyword_metadata, indent=2), encoding="utf-8")

    logger.info("Generated %d keywords → %s", len(keyword_list), kw_list_path)
    return {"keyword_list": keyword_list, "keyword_metadata": keyword_metadata}


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _call_ollama(prompt: str, model: str, ollama_url: str) -> str:
    """Send *prompt* to Ollama and return the response text."""
    url = f"{ollama_url.rstrip('/')}/api/generate"
    payload = {"model": model, "prompt": prompt, "stream": False}
    try:
        resp = requests.post(url, json=payload, timeout=300)
        resp.raise_for_status()
        return resp.json().get("response", "")
    except requests.exceptions.ConnectionError as exc:
        raise ConnectionError(
            f"Could not connect to Ollama at {ollama_url}. "
            "Ensure Ollama is running: `ollama serve`"
        ) from exc


def _parse_response(raw: str) -> dict:
    """Extract the JSON object from the LLM response."""
    # Strip markdown code fences if present
    clean = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
    # Find first { ... } block
    match = re.search(r"\{.*\}", clean, re.DOTALL)
    if not match:
        logger.warning("LLM returned no JSON object; raw=%s", raw[:200])
        return {"entities": [], "dates_financials": [], "red_flags": [], "key_phrases": []}
    try:
        data = json.loads(match.group())
    except json.JSONDecodeError as exc:
        logger.warning("JSON decode error: %s", exc)
        return {"entities": [], "dates_financials": [], "red_flags": [], "key_phrases": []}

    # Ensure all expected keys exist
    for key in ("entities", "dates_financials", "red_flags", "key_phrases"):
        if key not in data or not isinstance(data[key], list):
            data[key] = []
    return data


def _flatten_and_deduplicate(categorised: dict) -> list[str]:
    """Merge all categories into a single deduplicated, normalised list."""
    seen: set[str] = set()
    result: list[str] = []
    for keywords in categorised.values():
        for kw in keywords:
            normalised = kw.strip().lower()
            if normalised and normalised not in seen:
                seen.add(normalised)
                result.append(kw.strip())
    return sorted(result, key=str.lower)


def _build_metadata(categorised: dict) -> list[dict]:
    """Return a list of ``{keyword, category}`` dicts."""
    meta: list[dict] = []
    category_map = {
        "entities": "entity",
        "dates_financials": "date_financial",
        "red_flags": "red_flag",
        "key_phrases": "key_phrase",
    }
    seen: set[str] = set()
    for raw_cat, keywords in categorised.items():
        category = category_map.get(raw_cat, raw_cat)
        for kw in keywords:
            normalised = kw.strip().lower()
            if normalised and normalised not in seen:
                seen.add(normalised)
                meta.append({"keyword": kw.strip(), "category": category})
    return meta
