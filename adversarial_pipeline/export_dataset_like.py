from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DATASET_JSON = REPO_ROOT / "datasets" / "VLAT_comprehensive_dataset_structured_fixed.json"


def _load_error_type_path_map() -> dict[str, list[str]]:
    obj = json.loads(DATASET_JSON.read_text(encoding="utf-8"))
    mapping: dict[str, list[str]] = {}
    for row in obj.get("qa_pairs", []):
        error_type = row.get("error_type")
        image_path = row.get("image_path")
        if not error_type or not image_path or error_type in mapping:
            continue
        parts = image_path.replace("\\", "/").split("/")
        if len(parts) >= 3:
            mapping[error_type] = parts[:3]
    return mapping


def _resolve_json_dir(run_dir: Path, mode: str) -> tuple[Path, Path]:
    if mode == "aggregate_candidate":
        return run_dir / "aggregate" / "json", run_dir
    if mode == "aggregate_reviewed_valid":
        return run_dir / "aggregate_reviewed_valid_only" / "json", run_dir
    if mode == "reviewed_valid":
        return run_dir / "successful_reviewed" / "valid_success" / "json", run_dir
    return run_dir / "successful_only" / "json", run_dir


def _iter_source_records(run_dir: Path, mode: str) -> list[tuple[Path, dict, Path]]:
    json_dir, image_root = _resolve_json_dir(run_dir, mode)
    if not json_dir.exists():
        return []
    pairs: list[tuple[Path, dict, Path]] = []
    for path in sorted(json_dir.glob("*.json")):
        pairs.append((path, json.loads(path.read_text(encoding="utf-8")), image_root))
    return pairs


def _qa_payload(record: dict) -> dict:
    return {
        "question": record.get("question"),
        "options": {
            "A": record.get("option_A"),
            "B": record.get("option_B"),
            "C": record.get("option_C"),
            "D": record.get("option_D"),
        },
        "correctAnswer": record.get("correct_answer"),
        "wrongDueToMisleaderAnswer": record.get("misleading_answer"),
        "misleader": record.get("error_type"),
        "chartType": record.get("chart_type"),
        "task": record.get("task_mode"),
        "difficulty": None,
        "ifLabelled": "False",
        "explanation": record.get("qa_refactor", {}).get("reason") if isinstance(record.get("qa_refactor"), dict) else None,
        "source_chart_path": record.get("source_chart_path"),
        "generated_image_path": record.get("image_path"),
        "sample_id": record.get("sample_id"),
        "success_type": record.get("success_type"),
        "llm_judge": record.get("llm_judge"),
    }


def export_run(run_dir: Path, out_root: Path, mode: str) -> dict:
    path_map = _load_error_type_path_map()
    exported = []

    bucket_name = (
        "reviewed_valid_dataset"
        if mode in {"reviewed_valid", "aggregate_reviewed_valid"}
        else "candidate_dataset"
    )
    dataset_root = out_root / bucket_name
    dataset_root.mkdir(parents=True, exist_ok=True)

    for _, record, image_root in _iter_source_records(run_dir, mode):
        error_type = record.get("error_type")
        rel_parts = path_map.get(error_type)
        image_rel = record.get("image_path")
        if not error_type or not rel_parts or not image_rel:
            continue

        image_src = image_root / image_rel
        if not image_src.exists():
            continue

        layer_dir = dataset_root.joinpath(*rel_parts)
        qa_dir = layer_dir / "qa"
        layer_dir.mkdir(parents=True, exist_ok=True)
        qa_dir.mkdir(parents=True, exist_ok=True)

        image_name = f"{record['sample_id']}.png"
        qa_name = f"{record['sample_id']}.json"
        image_dst = layer_dir / image_name
        qa_dst = qa_dir / qa_name

        shutil.copy2(image_src, image_dst)
        qa_dst.write_text(json.dumps(_qa_payload(record), indent=2, ensure_ascii=False), encoding="utf-8")

        exported.append(
            {
                "sample_id": record["sample_id"],
                "error_type": error_type,
                "image_path": str(image_dst.relative_to(out_root)),
                "qa_path": str(qa_dst.relative_to(out_root)),
                "mode": mode,
            }
        )

    summary = {
        "run_dir": str(run_dir),
        "mode": mode,
        "exported_count": len(exported),
        "dataset_root": str(dataset_root),
        "records": exported,
    }
    summary_path = dataset_root / f"export_summary_{mode}.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export generated run outputs into dataset-like folder structure.")
    parser.add_argument("--run_dir", type=str, required=True)
    parser.add_argument("--out_root", type=str, required=True)
    parser.add_argument(
        "--mode",
        type=str,
        default="candidate",
        choices=["candidate", "reviewed_valid", "aggregate_candidate", "aggregate_reviewed_valid"],
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = export_run(Path(args.run_dir), Path(args.out_root), args.mode)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
