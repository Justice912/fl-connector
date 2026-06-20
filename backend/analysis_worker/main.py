from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .engine import analyze_project


def emit(progress: int, stage: str, message: str) -> None:
    print(
        json.dumps(
            {
                "type": "progress",
                "progress": progress,
                "stage": stage,
                "message": message,
            }
        ),
        flush=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze FL Connector reconstruction stems.")
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = analyze_project(args.project, emit)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        temporary.write_text(json.dumps(result, indent=2), encoding="utf-8")
        os.replace(temporary, args.output)
        emit(100, "complete", "Local analysis result written.")
        return 0
    except Exception as exc:
        print(str(exc), file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
