"""Tests for the Keyword Generation Agent modules."""

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from keyword_agent.case_manager import CaseManager, _sha256
from keyword_agent.keyword_generator import _flatten_and_deduplicate, _parse_response
from keyword_agent.text_extractor import _normalize


class TestCaseManager(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.manager = CaseManager(cases_root=str(self.tmp))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_create_case_generates_uuid(self):
        info = self.manager.create_case()
        self.assertIn("case_id", info)
        self.assertIn("case_dir", info)
        self.assertTrue(info["case_dir"].exists())

    def test_create_case_explicit_id(self):
        info = self.manager.create_case(case_id="TEST-001")
        self.assertEqual(info["case_id"], "TEST-001")

    def test_create_case_subdirs(self):
        info = self.manager.create_case(case_id="SUBDIRS")
        case_dir = info["case_dir"]
        for sub in ["input", "ocr_output", "extracted_text", "keywords",
                    "search_results", "evaluation", "reports"]:
            self.assertTrue((case_dir / sub).is_dir(), f"Missing subdir: {sub}")

    def test_create_case_manifest_created(self):
        info = self.manager.create_case(case_id="MANIFEST")
        manifest_path = info["case_dir"] / "file_manifest.json"
        self.assertTrue(manifest_path.exists())
        data = json.loads(manifest_path.read_text())
        self.assertIsInstance(data, list)
        self.assertEqual(data, [])

    def test_ingest_file_copies_and_records(self):
        # Create a temporary source file
        src = self.tmp / "evidence.txt"
        src.write_text("test evidence content", encoding="utf-8")

        info = self.manager.create_case(case_id="INGEST")
        case_dir = info["case_dir"]
        entry = self.manager.ingest_file(case_dir, src)

        self.assertEqual(entry["original_filename"], "evidence.txt")
        self.assertIn("sha256", entry)
        self.assertEqual(len(entry["sha256"]), 64)  # SHA-256 hex = 64 chars
        self.assertTrue((case_dir / entry["stored_path"]).exists())

        manifest = self.manager.load_manifest(case_dir)
        self.assertEqual(len(manifest), 1)
        self.assertEqual(manifest[0]["sha256"], entry["sha256"])

    def test_sha256_helper(self):
        f = self.tmp / "hash_test.txt"
        f.write_bytes(b"hello world")
        expected = hashlib.sha256(b"hello world").hexdigest()
        self.assertEqual(_sha256(f), expected)

    def test_ingest_file_does_not_modify_original(self):
        src = self.tmp / "original.txt"
        original_content = "do not modify"
        src.write_text(original_content, encoding="utf-8")

        info = self.manager.create_case(case_id="NOMOD")
        self.manager.ingest_file(info["case_dir"], src)

        self.assertEqual(src.read_text(encoding="utf-8"), original_content)


class TestNormalize(unittest.TestCase):
    def test_strips_excessive_whitespace(self):
        result = _normalize("hello   world")
        self.assertEqual(result, "hello world")

    def test_collapses_multiple_blank_lines(self):
        result = _normalize("line1\n\n\n\nline2")
        self.assertEqual(result, "line1\n\nline2")

    def test_strips_outer_whitespace(self):
        result = _normalize("  hello  ")
        self.assertEqual(result, "hello")

    def test_normalizes_unicode(self):
        # NFKC: ligature fi → fi
        result = _normalize("\ufb01rst")
        self.assertEqual(result, "first")


class TestParseResponse(unittest.TestCase):
    def test_valid_json(self):
        raw = json.dumps({
            "entities": ["Alice", "Acme Corp"],
            "dates_financials": ["2024-01-01"],
            "red_flags": ["bribery"],
            "key_phrases": ["supply chain"],
        })
        result = _parse_response(raw)
        self.assertEqual(result["entities"], ["Alice", "Acme Corp"])
        self.assertEqual(result["red_flags"], ["bribery"])

    def test_json_in_markdown_fence(self):
        raw = '```json\n{"entities": ["Bob"], "dates_financials": [], "red_flags": [], "key_phrases": []}\n```'
        result = _parse_response(raw)
        self.assertEqual(result["entities"], ["Bob"])

    def test_missing_keys_filled_with_empty_list(self):
        raw = '{"entities": ["X"]}'
        result = _parse_response(raw)
        self.assertEqual(result["dates_financials"], [])
        self.assertEqual(result["red_flags"], [])
        self.assertEqual(result["key_phrases"], [])

    def test_invalid_json_returns_defaults(self):
        result = _parse_response("not valid json at all")
        self.assertEqual(result["entities"], [])

    def test_no_json_returns_defaults(self):
        result = _parse_response("I could not find any keywords.")
        self.assertEqual(result["entities"], [])


class TestFlattenAndDeduplicate(unittest.TestCase):
    def test_deduplicates_case_insensitive(self):
        categorised = {
            "entities": ["Alice", "alice", "ALICE"],
            "dates_financials": [],
            "red_flags": [],
            "key_phrases": [],
        }
        result = _flatten_and_deduplicate(categorised)
        # Only one "Alice" should remain
        lower_result = [k.lower() for k in result]
        self.assertEqual(lower_result.count("alice"), 1)

    def test_sorted_output(self):
        categorised = {
            "entities": ["Zebra", "Apple"],
            "dates_financials": [],
            "red_flags": [],
            "key_phrases": [],
        }
        result = _flatten_and_deduplicate(categorised)
        self.assertEqual(result, sorted(result, key=str.lower))

    def test_empty_strings_excluded(self):
        categorised = {
            "entities": ["", "  ", "Valid"],
            "dates_financials": [],
            "red_flags": [],
            "key_phrases": [],
        }
        result = _flatten_and_deduplicate(categorised)
        self.assertNotIn("", result)
        self.assertNotIn("  ", result)


if __name__ == "__main__":
    unittest.main()
