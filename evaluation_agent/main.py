"""Evaluation Agent — CLI entry point.

Usage
-----
    python -m evaluation_agent --case-id <id>
    python -m evaluation_agent --case-id <id> --model mistral
    python -m evaluation_agent --case-id <id> --allegations "..."
    python -m evaluation_agent --case-id <id> --ollama-url http://...
    python -m evaluation_agent --case-id <id> --cases-root /path/to/cases
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from evaluation_agent.evaluator import (
    DEFAULT_MODEL,
    DEFAULT_OLLAMA_URL,
    evaluate_results,
    load_search_results,
)
from evaluation_agent.report_generator import generate_report

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    """Run the Evaluation Agent.

    Returns:
        0 on success, 1 on error.
    """
    args = _parse_args(argv)

    cases_root = Path(args.cases_root)
    case_dir = cases_root / args.case_id
    if not case_dir.exists():
        print(
            f"ERROR: Case directory not found: {case_dir}\n"
            "Run the Keyword Generation Agent first to create the case.",
            file=sys.stderr,
        )
        return 1

    print(f"\n{'='*60}")
    print(f"  Case ID : {args.case_id}")
    print(f"  Case dir: {case_dir.resolve()}")
    print(f"{'='*60}\n")

    # ------------------------------------------------------------------ Allegations
    allegations = args.allegations
    if not allegations:
        # Try to read from the allegations file written by keyword agent (if any)
        allegations_path = case_dir / "allegations.txt"
        if allegations_path.exists():
            allegations = allegations_path.read_text(encoding="utf-8").strip()
            print(f"  Loaded allegations from {allegations_path}")

    if not allegations:
        print("Enter allegations (press Enter twice to finish):")
        lines: list[str] = []
        try:
            while True:
                line = input()
                if line == "" and lines and lines[-1] == "":
                    break
                lines.append(line)
        except EOFError:
            pass
        allegations = "\n".join(lines).strip()

    if not allegations:
        print("ERROR: No allegations provided.  Aborting.", file=sys.stderr)
        return 1

    # ------------------------------------------------------------------ Load keyword metadata
    kw_meta_path = case_dir / "keywords" / "keyword_metadata.json"
    if kw_meta_path.exists():
        keyword_metadata = json.loads(kw_meta_path.read_text(encoding="utf-8"))
        print(f"  Loaded {len(keyword_metadata)} keywords from {kw_meta_path}")
    else:
        logger.warning("keyword_metadata.json not found; proceeding without keyword context")
        keyword_metadata = []

    # ------------------------------------------------------------------ Load search results
    search_results_dir = case_dir / "search_results"
    search_results = load_search_results(search_results_dir)
    if not search_results:
        print(
            f"  WARNING: No search result files found in {search_results_dir}.\n"
            "  Place CSV or JSON files there before running the Evaluation Agent.",
            file=sys.stderr,
        )
        return 1

    print(f"  Loaded {len(search_results)} search result(s) to evaluate")

    # ------------------------------------------------------------------ Evaluate
    print(f"\n  Evaluating with Ollama model '{args.model}'…\n")
    try:
        evaluated = evaluate_results(
            allegations=allegations,
            search_results=search_results,
            keyword_metadata=keyword_metadata,
            evaluation_dir=case_dir / "evaluation",
            model=args.model,
            ollama_url=args.ollama_url,
        )
    except ConnectionError as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        return 1

    # ------------------------------------------------------------------ Report
    report_path = generate_report(
        case_id=args.case_id,
        allegations=allegations,
        evaluation_results=evaluated,
        reports_dir=case_dir / "reports",
    )

    # ------------------------------------------------------------------ Summary
    relevant = [r for r in evaluated if r["verdict"] == "Relevant"]
    potential = [r for r in evaluated if r["verdict"] == "Potentially Relevant"]
    not_rel = [r for r in evaluated if r["verdict"] == "Not Relevant"]

    print(f"  ✓ Evaluation complete — {len(evaluated)} result(s)")
    print(f"    Relevant             : {len(relevant)}")
    print(f"    Potentially Relevant : {len(potential)}")
    print(f"    Not Relevant         : {len(not_rel)}")
    print()
    print(f"  evaluation_results.json → {case_dir / 'evaluation' / 'evaluation_results.json'}")
    print(f"  semantic_file.txt       → {case_dir / 'evaluation' / 'semantic_file.txt'}")
    print(f"  investigation_report.html → {report_path}")

    print(f"\n{'='*60}")
    print("  Evaluation complete.")
    print(f"  Case ID: {args.case_id}")
    print(f"{'='*60}\n")
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="evaluation_agent",
        description="Forensic AI Evaluation Agent",
    )
    parser.add_argument(
        "--case-id",
        required=True,
        metavar="ID",
        help="Case ID created by the Keyword Generation Agent",
    )
    parser.add_argument(
        "--allegations",
        metavar="TEXT",
        help="Free-text allegations (omit to enter interactively or load from case folder)",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        metavar="MODEL",
        help=f"Ollama model name (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--ollama-url",
        default=DEFAULT_OLLAMA_URL,
        metavar="URL",
        help=f"Ollama server base URL (default: {DEFAULT_OLLAMA_URL})",
    )
    parser.add_argument(
        "--cases-root",
        default="cases",
        metavar="DIR",
        help="Root directory for all cases (default: cases/)",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
