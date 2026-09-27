#!/usr/bin/env python3
"""Validate a portable travel choose-confirm pair analysis bundle."""

from __future__ import annotations

import json
import hashlib
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_TEXT = ("s" + "k-", "/" + "hipilot/", "aimemodeldev." + "myhexin.com")


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    manifest = json.loads((ROOT / "BUNDLE_MANIFEST.json").read_text(encoding="utf-8"))
    task_manifest = json.loads((ROOT / "task" / "manifest.json").read_text(encoding="utf-8"))
    rows = read_jsonl(ROOT / "records" / "runs.jsonl")

    require(len(task_manifest.get("samples", [])) == 2, "Task manifest must contain two paired samples")
    expected_runs = int(manifest.get("run_count", 0))
    expected_models = len(manifest.get("models", []))
    expected_screenshots = int(manifest.get("screenshot_count", 0))
    require(len(rows) == expected_runs, f"Expected {expected_runs} runs, found {len(rows)}")
    require({row.get("version_id") for row in rows} == {"clean", "misleading"}, "Condition mismatch")
    model_counts = Counter(row.get("model_slug") for row in rows)
    require(len(model_counts) == expected_models, f"Expected {expected_models} models, found {len(model_counts)}")
    require(all(count == 2 for count in model_counts.values()), f"Model pair counts invalid: {model_counts}")
    require(not any(row.get("outcome") == "agent_error" for row in rows), "Bundle contains agent_error")

    screenshot_count = 0
    for row in rows:
        model_slug = str(row["model_slug"])
        condition = str(row["version_id"])
        trace_path = ROOT / "traces" / model_slug / condition / "trace.json"
        require(trace_path.exists(), f"Missing split trace: {trace_path.relative_to(ROOT)}")
        for step in row.get("trace", []):
            screenshot = ROOT / str(step.get("screenshot", ""))
            require(screenshot.is_file(), f"Missing screenshot: {step.get('screenshot')}")
            require(not Path(str(step["screenshot"])).is_absolute(), "Screenshot path must be bundle-relative")
            screenshot_count += 1
    require(
        screenshot_count == expected_screenshots,
        f"Expected {expected_screenshots} screenshots, found {screenshot_count}",
    )
    for item in manifest.get("files", []):
        path = ROOT / str(item["path"])
        require(path.is_file(), f"Manifest file missing: {item['path']}")
        require(path.stat().st_size == item.get("bytes"), f"Manifest size mismatch: {item['path']}")
        require(sha256(path) == item.get("sha256"), f"Manifest checksum mismatch: {item['path']}")

    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() in {".png", ".jpg", ".jpeg"}:
            continue
        if path.stat().st_size > 5 * 1024 * 1024:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for token in FORBIDDEN_TEXT:
            require(token not in text, f"Forbidden text {token!r} in {path.relative_to(ROOT)}")
    require(not list(ROOT.rglob("*.log")), "Server logs must not be included")
    require(not list(ROOT.rglob("__pycache__")), "__pycache__ must not be included")

    print("travel choose-confirm pair analysis bundle validation passed")
    print(f"runs={len(rows)} models={len(model_counts)} screenshots={screenshot_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
