#!/usr/bin/env python3
"""Package only the 50 verified JSON files at the zip root."""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.validate_outputs import validate_submission


def main() -> int:
    result = validate_submission(REPO_ROOT)
    if result["status"] != "PASS":
        raise RuntimeError("Refusing to package a failing submission")
    names = [f"EC_{index:03d}.json" for index in range(1, 51)]
    archive = REPO_ROOT / "submission_outputs.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as handle:
        for name in names:
            handle.write(REPO_ROOT / "output" / name, arcname=name)
    with zipfile.ZipFile(archive) as handle:
        entries = handle.namelist()
    if entries != names:
        raise RuntimeError(f"Archive entry mismatch: {entries}")
    print(f"Created {archive}")
    print(f"Verified archive entries: {len(entries)} JSON files, no wrapper directory")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
