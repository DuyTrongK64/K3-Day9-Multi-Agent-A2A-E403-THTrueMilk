#!/usr/bin/env python3
"""Execute all 50 cases, overwriting prior outputs and trace."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agents.artifact_agent import ArtifactAgent
from agents.supervisor import SupervisorAgent
from core.constants import FRAMEWORK, MODEL_NAME, MODEL_PARAMETER_SIZE, MODEL_PROVIDER
from core.trace import TraceWriter
from data_access.repository import OlistRepository


def expected_case_paths(root: Path) -> list[Path]:
    expected = [root / "input" / f"EC_{index:03d}.json" for index in range(1, 51)]
    missing = [path.name for path in expected if not path.is_file()]
    actual = sorted(path.name for path in (root / "input").glob("EC_*.json"))
    if missing or actual != [path.name for path in expected]:
        raise ValueError(f"Input set must be exactly EC_001..EC_050; missing={missing}")
    return expected


def clean_output(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for path in output_dir.iterdir():
        if path.is_file():
            path.unlink()
        else:
            raise ValueError(f"Unexpected directory inside output/: {path.name}")


def main() -> int:
    cases = expected_case_paths(REPO_ROOT)
    clean_output(REPO_ROOT / "output")
    trace = TraceWriter(REPO_ROOT / "trace.jsonl")
    trace.emit(
        "run_start",
        agent="SupervisorAgent",
        details={
            "case_count": len(cases),
            "model": MODEL_NAME,
            "parameter_size": MODEL_PARAMETER_SIZE,
            "provider": MODEL_PROVIDER,
            "framework": FRAMEWORK,
            "runtime": f"Python {sys.version.split()[0]}",
        },
    )
    repository = OlistRepository(REPO_ROOT / "data")
    supervisor = SupervisorAgent(repository, trace, REPO_ROOT / "output")
    completed = 0
    for case_path in cases:
        supervisor.run_case(case_path)
        completed += 1
    trace.emit(
        "run_summary", agent="SupervisorAgent",
        details={"expected": 50, "completed": completed, "status": "PASS"},
    )

    artifact = ArtifactAgent()
    trace.emit("agent_start", agent=artifact.name,
               details={"task": "create_and_validate_artifacts", "input_refs": ["run:summary"]})
    metadata_path = artifact.write_metadata(REPO_ROOT, completed)
    artifact.validate_artifacts(REPO_ROOT)
    trace.emit("agent_result", agent=artifact.name,
               details={"task": "create_and_validate_artifacts", "status": "completed",
                        "metadata": metadata_path.name})
    trace.emit("handoff", agent=artifact.name,
               details={"sender": artifact.name, "recipient": "SupervisorAgent",
                        "status": "completed"})
    print(f"Generated {completed} verified case outputs.")
    print(f"Trace: {REPO_ROOT / 'trace.jsonl'}")
    print(f"Metadata: {metadata_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
