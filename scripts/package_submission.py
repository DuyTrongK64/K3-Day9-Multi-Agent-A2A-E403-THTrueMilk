#!/usr/bin/env python3
"""Package the verified output/ directory in the format accepted by the portal."""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.validate_outputs import validate_submission


def expected_archive_entries() -> list[str]:
    return ["output/"] + [f"output/EC_{index:03d}.json" for index in range(1, 51)]


def create_archive(root: Path, archive: Path) -> list[str]:
    """Create a ZIP containing the output directory and exactly 50 JSON children."""
    names = [f"EC_{index:03d}.json" for index in range(1, 51)]
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as handle:
        # The submission portal expects the directory entry and output/ prefix.
        handle.write(root / "output", arcname="output")
        for name in names:
            handle.write(root / "output" / name, arcname=f"output/{name}")
    with zipfile.ZipFile(archive) as handle:
        entries = handle.namelist()
        corrupt_entry = handle.testzip()
    if entries != expected_archive_entries():
        raise RuntimeError(f"Archive entry mismatch: {entries}")
    if corrupt_entry is not None:
        raise RuntimeError(f"Archive CRC failure: {corrupt_entry}")
    return entries


def main() -> int:
    result = validate_submission(REPO_ROOT)
    if result["status"] != "PASS":
        raise RuntimeError("Refusing to package a failing submission")
    archive = REPO_ROOT / "output.zip"
    entries = create_archive(REPO_ROOT, archive)
    print(f"Created {archive}")
    print(
        f"Verified archive entries: {len(entries)} total "
        "(output/ directory + 50 JSON files)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
