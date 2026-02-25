"""Case manager: initialises a case folder structure and records file manifests."""

import hashlib
import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path


CASE_SUBDIRS = [
    "input",
    "ocr_output",
    "extracted_text",
    "keywords",
    "search_results",
    "evaluation",
    "reports",
]


class CaseManager:
    """Creates and manages the case directory structure for a forensic investigation."""

    def __init__(self, cases_root: str = "cases"):
        self.cases_root = Path(cases_root)

    def create_case(self, case_id: str | None = None) -> dict:
        """Create a new case directory structure.

        Args:
            case_id: Optional case identifier.  Defaults to a new UUID4.

        Returns:
            A dict with ``case_id`` and ``case_dir`` (resolved Path).
        """
        if case_id is None:
            case_id = str(uuid.uuid4())

        case_dir = self.cases_root / case_id
        for subdir in CASE_SUBDIRS:
            (case_dir / subdir).mkdir(parents=True, exist_ok=True)

        manifest_path = case_dir / "file_manifest.json"
        if not manifest_path.exists():
            manifest_path.write_text(json.dumps([], indent=2), encoding="utf-8")

        return {"case_id": case_id, "case_dir": case_dir.resolve()}

    def ingest_file(self, case_dir: Path, source_path: str | Path) -> dict:
        """Copy *source_path* into ``case_dir/input/`` and record its manifest entry.

        Args:
            case_dir: Root directory of the case (returned by :meth:`create_case`).
            source_path: Absolute or relative path to the evidence file.

        Returns:
            The manifest entry dict that was appended to ``file_manifest.json``.
        """
        source_path = Path(source_path)
        dest_path = case_dir / "input" / source_path.name
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        shutil.copy2(source_path, dest_path)

        sha256 = _sha256(dest_path)
        entry = {
            "original_filename": source_path.name,
            "stored_path": str(dest_path.relative_to(case_dir)),
            "sha256": sha256,
            "size_bytes": dest_path.stat().st_size,
            "ingested_at": datetime.now(timezone.utc).isoformat(),
        }

        manifest_path = case_dir / "file_manifest.json"
        manifest: list = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest.append(entry)
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        return entry

    def load_manifest(self, case_dir: Path) -> list:
        """Return the file manifest for *case_dir*."""
        manifest_path = case_dir / "file_manifest.json"
        if not manifest_path.exists():
            return []
        return json.loads(manifest_path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha256(path: Path) -> str:
    """Compute the SHA-256 hex digest of the file at *path*."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
