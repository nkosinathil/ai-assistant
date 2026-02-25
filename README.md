# Forensic AI Investigation System

Forensic AI Agents — keyword analysis and reporting powered by **Ollama** (fully offline LLM).

## Overview

Two cooperating agents form an end-to-end forensic investigation workflow:

| Agent | Module | Purpose |
|-------|--------|---------|
| **Keyword Generation Agent** | `keyword_agent` | Ingests allegations + evidence files → produces a keyword list |
| **Evaluation Agent** | `evaluation_agent` | Scores keyword search results against allegations → HTML report |

Both agents run **entirely offline** using a local Ollama instance.

---

## Requirements

- Python 3.12+
- [Ollama](https://ollama.ai) running locally (`ollama serve`)
- Tesseract OCR installed (`tesseract` in PATH) — required only for image/scanned-PDF evidence
- Poppler utilities (`pdftoppm`) — required only for scanned PDFs

Install Python dependencies:

```bash
pip install -r requirements.txt
```

---

## Agent 1 — Keyword Generation Agent

### What it does

1. Creates a structured case folder (`cases/<case-id>/`).
2. Ingests evidence files (PDF, DOCX, XLSX, EML, MSG, TXT, PNG, JPG, TIFF, BMP, scanned PDFs).
3. Computes SHA-256 hashes of all ingested files and logs them to `file_manifest.json`.
4. Extracts text from documents; runs Tesseract OCR on image-based evidence.
5. Sends all text to Ollama → extracts entities, dates/financials, red-flag terms, key phrases.
6. Writes `keywords/keyword_list.txt` and `keywords/keyword_metadata.json`.

### Usage

```bash
# Interactive mode (prompts for allegations, no files)
python -m keyword_agent

# Provide allegations and files inline
python -m keyword_agent \
  --allegations "Suspect diverted funds to shell companies." \
  --files evidence.pdf scanned_receipt.png \
  --model llama3

# Resume / continue an existing case
python -m keyword_agent --case-id <existing-case-id>

# All options
python -m keyword_agent --help
```

### Outputs (inside `cases/<case-id>/`)

| File | Description |
|------|-------------|
| `input/` | Original evidence files (copies — originals never modified) |
| `ocr_output/` | OCR-extracted text from images and scanned PDFs |
| `extracted_text/` | Text extracted from structured documents |
| `keywords/keyword_list.txt` | One keyword per line |
| `keywords/keyword_metadata.json` | Keywords with category metadata |
| `file_manifest.json` | SHA-256 hashes and ingestion timestamps |

---

## Agent 2 — Evaluation Agent

### What it does

1. Loads the keyword metadata from Agent 1.
2. Loads keyword search results from `cases/<case-id>/search_results/` (CSV or JSON files).
3. For each result, prompts Ollama to score relevance/confidence and assign a verdict.
4. Writes `evaluation/evaluation_results.json` and `evaluation/semantic_file.txt`.
5. Renders an HTML report at `reports/investigation_report.html`.

### Search result input schema

Place `.json` or `.csv` files in `cases/<case-id>/search_results/` before running.

Expected fields per record:

```json
{
  "filename": "document.pdf",
  "filepath": "relative/path/to/document.pdf",
  "matched_keywords": ["keyword1", "keyword2"],
  "snippet": "...text excerpt showing the match context..."
}
```

### Usage

```bash
python -m evaluation_agent --case-id <case-id>

# All options
python -m evaluation_agent --help
```

### Outputs (inside `cases/<case-id>/`)

| File | Description |
|------|-------------|
| `evaluation/evaluation_results.json` | Scored verdict for every search result |
| `evaluation/semantic_file.txt` | LLM evaluation brief |
| `reports/investigation_report.html` | Full HTML forensic report |

---

## Running Tests

```bash
python -m pytest tests/ -v
```

---

## Project Structure

```
.
├── keyword_agent/
│   ├── __init__.py
│   ├── main.py               # CLI entry point (python -m keyword_agent)
│   ├── case_manager.py       # Case folder creation, file ingestion, manifest
│   ├── ocr_processor.py      # Tesseract OCR for images and scanned PDFs
│   ├── text_extractor.py     # Text extraction (PDF/DOCX/XLSX/EML/MSG/TXT)
│   └── keyword_generator.py  # Ollama LLM keyword extraction
├── evaluation_agent/
│   ├── __init__.py
│   ├── main.py               # CLI entry point (python -m evaluation_agent)
│   ├── evaluator.py          # LLM evaluation with relevance scoring
│   └── report_generator.py   # HTML report rendering (Jinja2)
├── tests/
│   ├── test_keyword_agent.py
│   └── test_evaluation_agent.py
├── requirements.txt
└── README.md
```
