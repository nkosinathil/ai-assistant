"""Keyword Generation Agent — CLI entry point.

Usage
-----
    python -m keyword_agent                         # interactive mode
    python -m keyword_agent --case-id <id>          # resume / specify case ID
    python -m keyword_agent --allegations "..."     # provide allegations inline
    python -m keyword_agent --files file1 file2     # attach evidence files
    python -m keyword_agent --model mistral         # choose Ollama model
    python -m keyword_agent --ollama-url http://... # custom Ollama URL
    python -m keyword_agent --cases-root /path      # custom cases root dir
"""

import argparse
import logging
import sys
from pathlib import Path

from keyword_agent.case_manager import CaseManager
from keyword_agent.keyword_generator import DEFAULT_MODEL, DEFAULT_OLLAMA_URL, generate_keywords
from keyword_agent.ocr_processor import IMAGE_EXTENSIONS, is_image_based, process_file
from keyword_agent.text_extractor import SUPPORTED_EXTENSIONS, extract

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    """Run the Keyword Generation Agent.

    Returns:
        0 on success, 1 on error.
    """
    args = _parse_args(argv)

    # ------------------------------------------------------------------ Case setup
    manager = CaseManager(cases_root=args.cases_root)
    case_info = manager.create_case(case_id=args.case_id)
    case_id: str = case_info["case_id"]
    case_dir: Path = case_info["case_dir"]
    print(f"\n{'='*60}")
    print(f"  Case ID : {case_id}")
    print(f"  Case dir: {case_dir}")
    print(f"{'='*60}\n")

    # ------------------------------------------------------------------ Allegations
    allegations = args.allegations
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

    # ------------------------------------------------------------------ File ingestion
    evidence_files: list[Path] = []
    for f in (args.files or []):
        p = Path(f)
        if not p.exists():
            logger.warning("File not found, skipping: %s", p)
            continue
        entry = manager.ingest_file(case_dir, p)
        evidence_files.append(case_dir / entry["stored_path"])
        print(f"  Ingested: {p.name}  (sha256={entry['sha256'][:16]}…)")

    # ------------------------------------------------------------------ Text extraction
    text_chunks: list[str] = [f"[ALLEGATIONS]\n{allegations}"]

    for fp in evidence_files:
        ext = fp.suffix.lower()

        if is_image_based(fp):
            print(f"  OCR processing: {fp.name}")
            result = process_file(fp, case_dir / "ocr_output")
            if result["error"]:
                logger.warning("OCR error for %s: %s", fp.name, result["error"])
            elif result["text"]:
                text_chunks.append(f"[OCR: {fp.name}]\n{result['text']}")

        if ext in SUPPORTED_EXTENSIONS:
            print(f"  Extracting text: {fp.name}")
            result = extract(fp, case_dir / "extracted_text")
            if result["error"]:
                logger.warning("Extraction error for %s: %s", fp.name, result["error"])
            elif result["text"]:
                text_chunks.append(f"[DOCUMENT: {fp.name}]\n{result['text']}")

    combined_text = "\n\n".join(text_chunks)

    # ------------------------------------------------------------------ Keyword generation
    print(f"\n  Sending {len(combined_text):,} chars to Ollama model '{args.model}'…")
    try:
        result = generate_keywords(
            combined_text=combined_text,
            output_dir=case_dir / "keywords",
            model=args.model,
            ollama_url=args.ollama_url,
        )
    except ConnectionError as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        return 1

    kw_count = len(result["keyword_list"])
    print(f"\n  ✓ {kw_count} keywords generated")
    print(f"    keyword_list.txt     → {case_dir / 'keywords' / 'keyword_list.txt'}")
    print(f"    keyword_metadata.json → {case_dir / 'keywords' / 'keyword_metadata.json'}")
    print(f"    file_manifest.json   → {case_dir / 'file_manifest.json'}")
    print()

    # Print sample keywords
    sample = result["keyword_list"][:20]
    if sample:
        print("  Sample keywords:")
        for kw in sample:
            print(f"    • {kw}")
        if kw_count > 20:
            print(f"    … and {kw_count - 20} more")

    print(f"\n{'='*60}")
    print("  Keyword Generation complete.")
    print(f"  Case ID: {case_id}")
    print(f"{'='*60}\n")
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="keyword_agent",
        description="Forensic AI Keyword Generation Agent",
    )
    parser.add_argument(
        "--case-id",
        metavar="ID",
        help="Existing case ID to resume (default: new UUID)",
    )
    parser.add_argument(
        "--allegations",
        metavar="TEXT",
        help="Free-text allegations (omit to enter interactively)",
    )
    parser.add_argument(
        "--files",
        nargs="*",
        metavar="FILE",
        help="Evidence files to ingest (PDF, DOCX, XLSX, EML, MSG, TXT, PNG, JPG, …)",
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
