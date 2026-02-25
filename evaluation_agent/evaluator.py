"""Evaluator: sends search results to Ollama and scores each result against allegations."""

import json
import logging
import re
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "llama3"

EVALUATION_PROMPT_TEMPLATE = """You are a senior forensic analyst assistant.

ORIGINAL ALLEGATIONS:
{allegations}

KEYWORD LIST (with categories):
{keywords_block}

You are evaluating the following document search result from a forensic keyword search:

Filename: {filename}
File path: {filepath}
Matched keywords: {matched_keywords}
Text snippet: {snippet}

Evaluate this result for evidentiary relevance to the allegations above.

Return ONLY a JSON object in this exact format (no markdown, no explanation):
{{
  "relevance_score": <float 0.0-1.0>,
  "confidence_score": <float 0.0-1.0>,
  "verdict": "<Relevant|Potentially Relevant|Not Relevant>",
  "reasoning": "<one or two sentences>",
  "matched_allegations": "<which parts of the allegations this file relates to>"
}}
"""

VALID_VERDICTS = {"Relevant", "Potentially Relevant", "Not Relevant"}


def load_search_results(search_results_dir: Path) -> list[dict]:
    """Load all CSV/JSON search result files from *search_results_dir*.

    Args:
        search_results_dir: The ``search_results/`` sub-directory of a case folder.

    Returns:
        A combined list of search result records.
    """
    records: list[dict] = []
    if not search_results_dir.exists():
        return records

    for path in sorted(search_results_dir.iterdir()):
        if path.suffix.lower() == ".json":
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    records.extend(data)
                elif isinstance(data, dict):
                    records.append(data)
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning("Could not load %s: %s", path, exc)

        elif path.suffix.lower() == ".csv":
            try:
                import csv  # noqa: PLC0415

                with path.open(newline="", encoding="utf-8") as fh:
                    reader = csv.DictReader(fh)
                    for row in reader:
                        # Parse matched_keywords if stored as a JSON string
                        if "matched_keywords" in row and isinstance(row["matched_keywords"], str):
                            try:
                                row["matched_keywords"] = json.loads(row["matched_keywords"])
                            except (json.JSONDecodeError, TypeError):
                                row["matched_keywords"] = [
                                    k.strip() for k in row["matched_keywords"].split(",")
                                ]
                        records.append(dict(row))
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning("Could not load %s: %s", path, exc)

    return records


def evaluate_results(
    allegations: str,
    search_results: list[dict],
    keyword_metadata: list[dict],
    evaluation_dir: Path,
    model: str = DEFAULT_MODEL,
    ollama_url: str = DEFAULT_OLLAMA_URL,
) -> list[dict]:
    """Evaluate each search result with Ollama and write ``evaluation_results.json``.

    Args:
        allegations: The original free-text allegations.
        search_results: List of search result records (from :func:`load_search_results`).
        keyword_metadata: List of ``{keyword, category}`` dicts from Agent 1.
        evaluation_dir: The ``evaluation/`` sub-directory of the case folder.
        model: Ollama model name.
        ollama_url: Base URL of the Ollama API server.

    Returns:
        List of enriched evaluation result dicts.
    """
    evaluation_dir.mkdir(parents=True, exist_ok=True)

    keywords_block = _build_keywords_block(keyword_metadata)
    evaluated: list[dict] = []

    for i, record in enumerate(search_results, start=1):
        filename = record.get("filename", "unknown")
        logger.info("Evaluating [%d/%d]: %s", i, len(search_results), filename)

        prompt = EVALUATION_PROMPT_TEMPLATE.format(
            allegations=allegations[:4000],
            keywords_block=keywords_block[:2000],
            filename=filename,
            filepath=record.get("filepath", ""),
            matched_keywords=", ".join(record.get("matched_keywords") or []),
            snippet=(record.get("snippet") or "")[:1000],
        )

        raw_response = _call_ollama(prompt, model=model, ollama_url=ollama_url)
        scores = _parse_evaluation(raw_response)

        result = {
            "filename": filename,
            "filepath": record.get("filepath", ""),
            "matched_keywords": record.get("matched_keywords") or [],
            "snippet": record.get("snippet") or "",
            "relevance_score": scores["relevance_score"],
            "confidence_score": scores["confidence_score"],
            "verdict": scores["verdict"],
            "reasoning": scores["reasoning"],
            "matched_allegations": scores["matched_allegations"],
        }
        evaluated.append(result)

    # Write evaluation_results.json
    results_path = evaluation_dir / "evaluation_results.json"
    results_path.write_text(json.dumps(evaluated, indent=2), encoding="utf-8")
    logger.info("Wrote %d evaluation results → %s", len(evaluated), results_path)

    # Write semantic_file.txt (structured evaluation brief)
    _write_semantic_file(allegations, keyword_metadata, evaluation_dir)

    return evaluated


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _build_keywords_block(keyword_metadata: list[dict]) -> str:
    lines: list[str] = []
    for item in keyword_metadata:
        lines.append(f"  [{item.get('category', 'unknown')}] {item.get('keyword', '')}")
    return "\n".join(lines)


def _call_ollama(prompt: str, model: str, ollama_url: str) -> str:
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


def _parse_evaluation(raw: str) -> dict:
    clean = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
    match = re.search(r"\{.*\}", clean, re.DOTALL)
    default = {
        "relevance_score": 0.0,
        "confidence_score": 0.0,
        "verdict": "Not Relevant",
        "reasoning": "Could not parse LLM response.",
        "matched_allegations": "",
    }
    if not match:
        logger.warning("No JSON in LLM evaluation response; raw=%s", raw[:200])
        return default

    try:
        data = json.loads(match.group())
    except json.JSONDecodeError:
        return default

    # Clamp scores
    def _clamp(v, default_v: float) -> float:
        try:
            return max(0.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            return default_v

    verdict = data.get("verdict", "Not Relevant")
    if verdict not in VALID_VERDICTS:
        verdict = "Not Relevant"

    return {
        "relevance_score": _clamp(data.get("relevance_score"), 0.0),
        "confidence_score": _clamp(data.get("confidence_score"), 0.0),
        "verdict": verdict,
        "reasoning": str(data.get("reasoning", "")),
        "matched_allegations": str(data.get("matched_allegations", "")),
    }


def _write_semantic_file(
    allegations: str, keyword_metadata: list[dict], evaluation_dir: Path
) -> None:
    lines = [
        "FORENSIC SEMANTIC EVALUATION BRIEF",
        "=" * 60,
        "",
        "ALLEGATIONS:",
        allegations,
        "",
        "KEYWORD CATEGORIES:",
        _build_keywords_block(keyword_metadata),
        "",
        "EVALUATION INSTRUCTIONS:",
        "  For each search result, assess:",
        "  1. Relevance to the allegations (score 0.0–1.0)",
        "  2. Confidence in the assessment (score 0.0–1.0)",
        "  3. Overall verdict: Relevant | Potentially Relevant | Not Relevant",
        "  4. Brief reasoning and which allegation(s) the result connects to.",
    ]
    path = evaluation_dir / "semantic_file.txt"
    path.write_text("\n".join(lines), encoding="utf-8")
