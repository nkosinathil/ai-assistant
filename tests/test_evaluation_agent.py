"""Tests for the Evaluation Agent modules."""

import csv
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from evaluation_agent.evaluator import _parse_evaluation, load_search_results
from evaluation_agent.report_generator import generate_report


class TestParseEvaluation(unittest.TestCase):
    def test_valid_json(self):
        raw = json.dumps({
            "relevance_score": 0.9,
            "confidence_score": 0.8,
            "verdict": "Relevant",
            "reasoning": "Strong match.",
            "matched_allegations": "Allegation 1",
        })
        result = _parse_evaluation(raw)
        self.assertAlmostEqual(result["relevance_score"], 0.9)
        self.assertAlmostEqual(result["confidence_score"], 0.8)
        self.assertEqual(result["verdict"], "Relevant")
        self.assertEqual(result["reasoning"], "Strong match.")

    def test_scores_clamped_to_range(self):
        raw = json.dumps({
            "relevance_score": 1.5,
            "confidence_score": -0.3,
            "verdict": "Relevant",
            "reasoning": "test",
            "matched_allegations": "",
        })
        result = _parse_evaluation(raw)
        self.assertEqual(result["relevance_score"], 1.0)
        self.assertEqual(result["confidence_score"], 0.0)

    def test_invalid_verdict_defaults_to_not_relevant(self):
        raw = json.dumps({
            "relevance_score": 0.5,
            "confidence_score": 0.5,
            "verdict": "Completely Wrong",
            "reasoning": "test",
            "matched_allegations": "",
        })
        result = _parse_evaluation(raw)
        self.assertEqual(result["verdict"], "Not Relevant")

    def test_no_json_returns_defaults(self):
        result = _parse_evaluation("The document is not relevant at all.")
        self.assertEqual(result["relevance_score"], 0.0)
        self.assertEqual(result["verdict"], "Not Relevant")
        self.assertIn("Could not parse", result["reasoning"])

    def test_markdown_fence_stripped(self):
        raw = '```json\n{"relevance_score": 0.7, "confidence_score": 0.6, "verdict": "Potentially Relevant", "reasoning": "maybe", "matched_allegations": "para 2"}\n```'
        result = _parse_evaluation(raw)
        self.assertEqual(result["verdict"], "Potentially Relevant")
        self.assertAlmostEqual(result["relevance_score"], 0.7)


class TestLoadSearchResults(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_load_json_list(self):
        data = [
            {"filename": "a.pdf", "filepath": "/a.pdf", "matched_keywords": ["fraud"], "snippet": "text"}
        ]
        (self.tmp / "results.json").write_text(json.dumps(data), encoding="utf-8")
        results = load_search_results(self.tmp)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["filename"], "a.pdf")

    def test_load_json_single_dict(self):
        data = {"filename": "b.pdf", "filepath": "/b.pdf", "matched_keywords": [], "snippet": ""}
        (self.tmp / "single.json").write_text(json.dumps(data), encoding="utf-8")
        results = load_search_results(self.tmp)
        self.assertEqual(len(results), 1)

    def test_load_csv(self):
        csv_path = self.tmp / "results.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=["filename", "filepath", "matched_keywords", "snippet"])
            writer.writeheader()
            writer.writerow({
                "filename": "c.docx",
                "filepath": "/c.docx",
                "matched_keywords": '["bribe"]',
                "snippet": "some text",
            })
        results = load_search_results(self.tmp)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["filename"], "c.docx")
        self.assertEqual(results[0]["matched_keywords"], ["bribe"])

    def test_empty_dir_returns_empty_list(self):
        empty = self.tmp / "empty_dir"
        empty.mkdir()
        results = load_search_results(empty)
        self.assertEqual(results, [])

    def test_nonexistent_dir_returns_empty_list(self):
        results = load_search_results(self.tmp / "does_not_exist")
        self.assertEqual(results, [])


class TestReportGenerator(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _sample_results(self):
        return [
            {
                "filename": "doc1.pdf",
                "filepath": "/docs/doc1.pdf",
                "matched_keywords": ["fraud", "bribe"],
                "snippet": "Evidence of bribery found.",
                "relevance_score": 0.95,
                "confidence_score": 0.90,
                "verdict": "Relevant",
                "reasoning": "Direct match to allegations.",
                "matched_allegations": "Allegation 1",
            },
            {
                "filename": "doc2.xlsx",
                "filepath": "/docs/doc2.xlsx",
                "matched_keywords": ["payment"],
                "snippet": "Regular payment records.",
                "relevance_score": 0.3,
                "confidence_score": 0.4,
                "verdict": "Not Relevant",
                "reasoning": "Routine payments only.",
                "matched_allegations": "",
            },
        ]

    def test_report_file_created(self):
        report_path = generate_report(
            case_id="TEST-001",
            allegations="Suspect misused funds.",
            evaluation_results=self._sample_results(),
            reports_dir=self.tmp,
        )
        self.assertTrue(report_path.exists())
        self.assertEqual(report_path.name, "investigation_report.html")

    def test_report_contains_case_id(self):
        report_path = generate_report(
            case_id="CASE-XYZ",
            allegations="Test allegations.",
            evaluation_results=self._sample_results(),
            reports_dir=self.tmp,
        )
        html = report_path.read_text(encoding="utf-8")
        self.assertIn("CASE-XYZ", html)

    def test_report_contains_verdict_badges(self):
        report_path = generate_report(
            case_id="BADGES",
            allegations="Test.",
            evaluation_results=self._sample_results(),
            reports_dir=self.tmp,
        )
        html = report_path.read_text(encoding="utf-8")
        self.assertIn("Relevant", html)
        self.assertIn("Not Relevant", html)

    def test_report_contains_filenames(self):
        report_path = generate_report(
            case_id="FILES",
            allegations="Test.",
            evaluation_results=self._sample_results(),
            reports_dir=self.tmp,
        )
        html = report_path.read_text(encoding="utf-8")
        self.assertIn("doc1.pdf", html)
        self.assertIn("doc2.xlsx", html)

    def test_empty_results_report(self):
        report_path = generate_report(
            case_id="EMPTY",
            allegations="No results.",
            evaluation_results=[],
            reports_dir=self.tmp,
        )
        html = report_path.read_text(encoding="utf-8")
        self.assertIn("EMPTY", html)
        self.assertIn("0", html)  # totals show 0


if __name__ == "__main__":
    unittest.main()
