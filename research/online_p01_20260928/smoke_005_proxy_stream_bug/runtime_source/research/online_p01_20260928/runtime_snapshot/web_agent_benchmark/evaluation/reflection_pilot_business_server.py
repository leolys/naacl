#!/usr/bin/env python3
"""Start the Business shell with every generated artifact redirected per cell."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from web_agent_benchmark.business_shell import business_shell_app as shell


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--submissions", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--manual-review", type=Path, required=True)
    args = parser.parse_args()
    app = shell.make_app(
        args.tasks,
        args.submissions,
        args.summary,
        manual_review_path=args.manual_review,
        review_ui=False,
    )
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
