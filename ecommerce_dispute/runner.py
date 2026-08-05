from __future__ import annotations

import argparse
import json
from pathlib import Path

from .coordinator import CoordinatorAgent
from .domain import MODEL_NAME, MODEL_PARAMETER_SIZE, POLICY_VERSION, case_from_json
from .repository import OlistRepository


def run(input_dir: Path, output_dir: Path, data_dir: Path, trace_path: Path, metadata_path: Path) -> int:
    repository = OlistRepository(data_dir)
    coordinator = CoordinatorAgent(repository)
    output_dir.mkdir(parents=True, exist_ok=True)
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    for stale_output in output_dir.glob("EC_*.json"):
        stale_output.unlink()

    input_files = sorted(path for path in input_dir.glob("EC_*.json") if path.is_file())
    trace_events: list[dict] = []
    written = 0
    for input_file in input_files:
        payload = json.loads(input_file.read_text(encoding="utf-8"))
        case = case_from_json(payload)
        if case.policy_version != POLICY_VERSION:
            raise ValueError(f"{case.case_id}: unsupported policy version {case.policy_version}")
        output, case_trace = coordinator.run_case(case)
        (output_dir / input_file.name).write_text(
            json.dumps(output, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        trace_events.extend(case_trace)
        written += 1

    trace_path.write_text(
        "".join(json.dumps(event, ensure_ascii=False) + "\n" for event in trace_events),
        encoding="utf-8",
    )
    metadata = {
        "model": MODEL_NAME,
        "parameter_size": MODEL_PARAMETER_SIZE,
        "uses_llm": False,
        "max_allowed_parameter_size": "10B",
        "framework": "stdlib deterministic multi-agent pipeline",
        "runtime": "Python 3.13",
        "policy_version": POLICY_VERSION,
        "cases_processed": written,
        "input_dir": str(input_dir),
        "output_dir": str(output_dir),
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Run deterministic Olist dispute resolution.")
    parser.add_argument("--input-dir", type=Path, default=Path("input"))
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--trace-path", type=Path, default=Path("trace.jsonl"))
    parser.add_argument("--metadata-path", type=Path, default=Path("metadata.json"))
    args = parser.parse_args()
    count = run(args.input_dir, args.output_dir, args.data_dir, args.trace_path, args.metadata_path)
    print(f"processed {count} case(s)")


if __name__ == "__main__":
    main()
