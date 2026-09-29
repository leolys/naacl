#!/usr/bin/env python3
"""Build a portable, sanitized analysis bundle for the travel task pair."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TASK_ROOT = REPO_ROOT / "travel_choose_confirm_review_sample"
DEFAULT_RECORD_ROOT = (
    REPO_ROOT
    / "web_agent_benchmark"
    / "pair_evaluation_records"
    / "travel_choose_confirm_pair_available_main_models_20260712"
)
DEFAULT_AUDIT_PATH = REPO_ROOT / "paper" / "travel_choose_confirm_pair_trace_audit_20260712.md"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "travel_choose_confirm_pair_analysis_bundle_20260712"


README = """# Travel Choose-Confirm Pair: Task and Complete Agent Traces

这个目录是可独立传递的分析包，包含一个 clean/misleading 配对网页任务，以及多个模型在两个条件下的全部执行轨迹。

## 内容

- `task/`：可离线启动的任务服务、clean/misleading 图表、manifest 和隐藏评分逻辑。
- `records/runs.jsonl`：全部完整机器可读记录。
- `records/failures.jsonl`：所有非 success 记录。
- `records/summary.md`：结果概览。
- `traces/<model>/<condition>/trace.json`：按模型和条件拆分的完整可读记录。
- `screenshots/<model>/<condition>/`：每一步浏览器截图。
- `hidden_submissions/`：完成提交时由任务服务写出的原始隐藏评分记录；timeout 条件没有该文件。
- `analysis/trace_audit.md`：候选轨迹比较和使用建议。
- `scripts/validate_bundle.py`：离线完整性和安全检查。
- `BUNDLE_MANIFEST.json`：计数、模型、结果分布和文件校验和。

## Pair 设计

两个条件共享用户目标、候选州、州与县记录、网页流程、确认动作、正确路线和评分目标。唯一干预是安全地图：

- Clean start: `/travel-clean/`
- Misleading start: `/travel/`
- Correct route: `KS -> Johnson County -> Yes`
- Designated misleading route: `IL -> Champaign County -> Yes`

因此该样本是完整的可执行 web-agent task pair，而不是两张独立图表。

## 阅读轨迹

每条 `trace.json` 包含：

- `trace[].url`：当前网页状态；
- `trace[].page_text_excerpt`：agent 当时可见的主要文本；
- `trace[].action`：执行动作及模型原始动作输出；
- `trace[].screenshot`：相对于本目录的截图路径；
- `submission.path_trace`：完成提交后生成的导航与分支信息；
- `submission.evaluation_hidden_from_agent`：提交后才写入的隐藏评分。

模型输出文本只能称为 model-emitted action text，不能视为对模型内部推理链的忠实访问。

## 隐私清理

为方便外部分析，本包移除了 API key、API endpoint、响应 ID 和后端 trace ID，并把机器绝对路径改成包内相对路径。浏览动作、页面文本、模型输出、token usage、评分和结果标签保持不变。

## 启动任务

```bash
python task/server.py --host 127.0.0.1 --port 8137
```

任务入口为 `http://127.0.0.1:8137/travel/` 和 `http://127.0.0.1:8137/travel-clean/`。`/review` 仅供任务设计者审查，不应提供给 agent。

## 验证

```bash
python scripts/validate_bundle.py
```
"""


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def sanitize_response_metadata(value: Any) -> Any:
    if isinstance(value, list):
        return [sanitize_response_metadata(item) for item in value]
    if not isinstance(value, dict):
        return value
    cleaned: dict[str, Any] = {}
    for key, item in value.items():
        if key in {"id", "trace_id"}:
            continue
        cleaned[key] = sanitize_response_metadata(item)
    return cleaned


def sanitize_row(row: dict[str, Any], record_root: Path, output_root: Path) -> dict[str, Any]:
    cleaned = sanitize_response_metadata(copy.deepcopy(row))
    run_config = cleaned.get("run_config")
    if isinstance(run_config, dict):
        run_config.pop("aime_base_url", None)
    model_slug = str(cleaned["model_slug"])
    condition = str(cleaned["version_id"])
    for step in cleaned.get("trace", []):
        screenshot = step.get("screenshot")
        if not screenshot:
            continue
        source = Path(screenshot)
        if not source.is_absolute():
            source = REPO_ROOT / source
        destination = output_root / "screenshots" / model_slug / condition / source.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        step["screenshot"] = destination.relative_to(output_root).as_posix()
    return cleaned


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def copy_task(task_root: Path, destination: Path) -> None:
    shutil.copytree(
        task_root,
        destination,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "submissions.jsonl"),
    )


def build(args: argparse.Namespace) -> None:
    task_root = args.task_root.resolve()
    record_root = args.record_root.resolve()
    audit_path = args.audit_path.resolve()
    output_root = args.output_root.resolve()
    if output_root.exists():
        raise SystemExit(f"Output already exists: {output_root}")

    output_root.mkdir(parents=True)
    copy_task(task_root, output_root / "task")

    source_rows = read_jsonl(record_root / "runs.jsonl")
    rows = [sanitize_row(row, record_root, output_root) for row in source_rows]
    write_jsonl(output_root / "records" / "runs.jsonl", rows)
    write_jsonl(
        output_root / "records" / "failures.jsonl",
        [row for row in rows if row.get("outcome") != "success"],
    )
    shutil.copy2(record_root / "summary.md", output_root / "records" / "summary.md")

    for row in rows:
        model_slug = str(row["model_slug"])
        condition = str(row["version_id"])
        trace_path = output_root / "traces" / model_slug / condition / "trace.json"
        trace_path.parent.mkdir(parents=True, exist_ok=True)
        trace_path.write_text(
            json.dumps(row, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        hidden_source = record_root / model_slug / "hidden_results" / f"{condition}.jsonl"
        if hidden_source.exists():
            hidden_destination = output_root / "hidden_submissions" / model_slug / f"{condition}.jsonl"
            hidden_destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(hidden_source, hidden_destination)

    audit_text = audit_path.read_text(encoding="utf-8")
    for source_path in (
        "web_agent_benchmark/pair_evaluation_records/"
        "travel_choose_confirm_pair_available_main_models_20260712/runs.jsonl",
        "web_agent_benchmark/pair_evaluation_records/"
        "travel_choose_confirm_pair_expanded_nine_models_20260712/runs.jsonl",
    ):
        audit_text = audit_text.replace(source_path, "records/runs.jsonl")
    analysis_path = output_root / "analysis" / "trace_audit.md"
    analysis_path.parent.mkdir(parents=True, exist_ok=True)
    analysis_path.write_text(audit_text, encoding="utf-8")

    validator_source = Path(__file__).with_name("validate_travel_choose_confirm_pair_bundle.py")
    scripts_dir = output_root / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(validator_source, scripts_dir / "validate_bundle.py")
    (output_root / "README_zh.md").write_text(README, encoding="utf-8")

    outcome_counts: dict[str, int] = {}
    for row in rows:
        outcome = str(row.get("outcome", "unknown"))
        outcome_counts[outcome] = outcome_counts.get(outcome, 0) + 1
    files = []
    for path in sorted(output_root.rglob("*")):
        if path.is_file() and path.name != "BUNDLE_MANIFEST.json":
            files.append(
                {
                    "path": path.relative_to(output_root).as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": sha256(path),
                }
            )
    manifest = {
        "bundle": "travel_choose_confirm_pair_analysis_bundle",
        "version": "20260712",
        "conditions": ["clean", "misleading"],
        "models": sorted({str(row["model_name"]) for row in rows}),
        "run_count": len(rows),
        "screenshot_count": sum(len(row.get("trace", [])) for row in rows),
        "outcome_counts": outcome_counts,
        "sanitization": {
            "removed": ["API keys", "API endpoint", "response IDs", "backend trace IDs", "absolute paths"],
            "preserved": ["browser actions", "visible page text", "model action text", "usage", "scores", "outcomes"],
        },
        "files": files,
    }
    (output_root / "BUNDLE_MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-root", type=Path, default=DEFAULT_TASK_ROOT)
    parser.add_argument("--record-root", type=Path, default=DEFAULT_RECORD_ROOT)
    parser.add_argument("--audit-path", type=Path, default=DEFAULT_AUDIT_PATH)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()
    build(args)
    print(args.output_root.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
