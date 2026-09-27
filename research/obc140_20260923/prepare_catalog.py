"""Prepare immutable original-140 charts and allowlisted public task records.

Purely offline: no model clients, browser sessions, remote writes, or clean arm.
The prior adapter owns the public allowlist. Select metadata is preserved by the
minimal extension below; its missing public option arrays are never invented.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / "competing_rules_20260923"
WORKSPACE = HERE.parents[1]
DEFAULT_SOURCE = WORKSPACE / ".aris/dataset_inventory_20260918/raw"
sys.path.insert(0, str(PREVIOUS))
from adapter import PUBLIC_KEYS, public_projection  # noqa: E402

DOMAINS = {"business47": 47, "public39": 39, "environment35": 35, "health19": 19}
SCHEMA_VERSION = "obc140_v1"
VISIBLE_TYPES = {"text", "textarea", "checkbox", "readonly", "select"}
READONLY_FIELDS = {
    "program_area", "review_scope", "record_workflow", "routing_criterion",
    "program_portfolio", "assessment_focus", "escalation_queue", "routing_basis",
    "review_window", "workflow_stage", "assessment_window", "target_workflow",
    "monitoring_focus", "routing_workflow", "operational_workflow",
    "review_timeframe", "reporting_year",
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def encoded(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def project_public(raw: dict, alias: str) -> dict:
    """Reuse the adapter; restore select type without guessing hidden options."""
    adapted = copy.deepcopy(raw)
    original_types = {}
    for item in adapted.get("companion_actions", []):
        kind = item.get("input_type", "text")
        if kind != "hidden" and kind not in VISIBLE_TYPES:
            raise ValueError("Unsupported companion type: " + str(kind))
        if kind == "select":
            original_types[str(item["field_id"])] = kind
            item["input_type"] = "text"
    public = public_projection(adapted, alias)
    for item in public["companion_fields"]:
        if item["field"] in original_types:
            item["type"] = original_types[item["field"]]
    if set(public) != PUBLIC_KEYS:
        raise ValueError("Public allowlist changed")
    return public


def load_sources(source_raw: Path):
    """Verify all official rows and charts against the existing offline audit."""
    source_raw = Path(source_raw).resolve()
    catalog_path = source_raw.parent / "TASK_CATALOG.json"
    previous_path = PREVIOUS / "panel140_manifest.json"
    audited = read_json(catalog_path)
    previous = read_json(previous_path)
    entries = {row["slug"]: row for row in audited}
    old_rows = {row["task_slug"]: row for row in previous["tasks"]}
    if len(audited) != 140 or len(entries) != 140 or set(entries) != set(old_rows):
        raise ValueError("Expected 140 unique, matching original catalog tasks")
    sources = {str(catalog_path): digest(catalog_path.read_bytes()),
               str(previous_path): digest(previous_path.read_bytes())}
    rows = []
    for domain, expected_count in DOMAINS.items():
        split = source_raw / "splits/official140" / (domain + "_tasks.jsonl")
        split_bytes = split.read_bytes()
        sources[str(split)] = digest(split_bytes)
        domain_count = 0
        for line_number, line in enumerate(split_bytes.splitlines(), 1):
            if not line.strip():
                continue
            raw = json.loads(line)
            slug = raw["task_slug"]
            entry, old = entries[slug], old_rows[slug]
            if raw.get("split") != "official140" or entry["domain"] != domain:
                raise ValueError("Unexpected condition or domain: " + slug)
            pair = old["pair_assets"]["official140"]
            if digest(line) != pair["record_sha256_excluding_line_ending"]:
                raise ValueError("Original task row changed: " + slug)
            figure_name = Path(raw["chart_asset"]["figure_path"]).name
            chart = source_raw / "assets/official140" / domain / slug / figure_name
            audited_relative = Path(entry["assets"]["figure_path"]["path"].replace("\\", "/"))
            if (source_raw.parent / audited_relative).resolve() != chart.resolve():
                raise ValueError("Conflicting original figure paths: " + slug)
            chart_bytes = chart.read_bytes()
            chart_hash = digest(chart_bytes)
            if chart_hash != entry["assets"]["figure_path"]["sha256"] or chart_hash != pair["sha256"]:
                raise ValueError("Original chart changed: " + slug)
            sources[str(chart)] = chart_hash
            rows.append({"raw": raw, "entry": entry, "old": old, "chart": chart,
                         "chart_bytes": chart_bytes, "chart_sha256": chart_hash,
                         "split": split, "line_number": line_number,
                         "source_row_sha256": digest(line), "domain": domain})
            domain_count += 1
        if domain_count != expected_count:
            raise ValueError("Unexpected official task count for " + domain)
    if len(rows) != 140 or {row["raw"]["task_slug"] for row in rows} != set(entries):
        raise ValueError("Official rows must contain exactly the audited 140 tasks")
    return sorted(rows, key=lambda row: row["raw"]["task_slug"]), sources


def companion_audit(rows):
    """Record the complete inspected public-context inventory, offline only."""
    counts, readonly, selects = Counter(), [], []
    for row in rows:
        slug = row["raw"]["task_slug"]
        for field in row["raw"].get("companion_actions", []):
            kind = field.get("input_type", "text")
            counts[kind] += 1
            if kind not in VISIBLE_TYPES | {"hidden"}:
                raise ValueError("Unsupported companion type for " + slug + ": " + str(kind))
            if kind == "readonly":
                if field["field_id"] not in READONLY_FIELDS or not isinstance(field.get("correct_value"), str):
                    raise ValueError("Unreviewed readonly public context for " + slug)
                readonly.append({"task_slug": slug, "field": field["field_id"],
                                 "label": field.get("field_label", field["field_id"]),
                                 "value": field["correct_value"],
                                 "assessment": "original_public_program_scope_or_workflow_context"})
            if kind == "select":
                if any(key in field for key in ("options", "option_labels", "choices")):
                    raise ValueError("Previously unreviewed select options for " + slug)
                selects.append({"task_slug": slug, "field": field["field_id"],
                                "label": field.get("field_label", field["field_id"]),
                                "required": bool(field.get("required", False))})
    return {
        "scope": "offline_preparation_audit_not_new_human_validation",
        "companion_type_counts": dict(sorted(counts.items())),
        "readonly_count": len(readonly), "readonly_fields": readonly,
        "readonly_policy": "Existing readonly public program, period, scope and workflow values are preserved; no chart-derived editable answer defaults are included.",
        "select_field_count": len(selects),
        "select_task_count": len({row["task_slug"] for row in selects}),
        "select_fields": selects,
        "select_limitation": "55 select fields in 37 tasks lack public option arrays in the source specification. Public records preserve field/label/type/required only, with no correct_value, guessed options, or default. This package supports static chain generation, not reconstructed form execution.",
        "unknown_visible_types": [],
    }


def compile_bundle(source_raw: Path):
    rows, sources = load_sources(source_raw)
    audit = companion_audit(rows)
    files, tasks = {}, []
    for index, row in enumerate(rows, 1):
        raw, entry, old = row["raw"], row["entry"], row["old"]
        slug, alias = raw["task_slug"], "task_%03d" % index
        directory = "data/" + alias
        chart_file = directory + "/chart" + row["chart"].suffix.lower()
        public_file, offline_file = directory + "/public.json", directory + "/offline.json"
        public = project_public(raw, alias)
        offline = {
            "task_slug": slug, "domain": row["domain"], "alias": alias,
            "condition": "official140", "role": "offline_human_review_only_never_model_input",
            "original_mechanism": entry["original_mechanism"],
            "audited_mechanism": entry["audited_mechanism"],
            "original_plot": entry["original_plot"], "audit_note": entry.get("audit_note", ""),
            "review_records": entry.get("review_records", []),
            "evidence_limit_flags": old.get("evidence_limit_flags", []),
            "raw": raw,
            "provenance": {"source_split": str(row["split"]),
                           "source_line_number": row["line_number"],
                           "source_row_sha256": row["source_row_sha256"],
                           "source_chart": str(row["chart"]),
                           "chart_sha256": row["chart_sha256"],
                           "public_sha256": digest(encoded(public))},
            "companion_projection_audit": {
                "readonly_fields": [item for item in audit["readonly_fields"] if item["task_slug"] == slug],
                "select_fields_without_public_options": [item for item in audit["select_fields"] if item["task_slug"] == slug],
            },
        }
        files[chart_file], files[public_file], files[offline_file] = row["chart_bytes"], encoded(public), encoded(offline)
        tasks.append({"task_slug": slug, "domain": row["domain"], "alias": alias,
                      "chart_file": chart_file, "public_file": public_file, "offline_file": offline_file})
    catalog = {"schema_version": SCHEMA_VERSION, "condition": "official140",
               "base_task_count": 140, "tasks": tasks}
    audit.update({"schema_version": SCHEMA_VERSION, "condition": "official140",
                  "base_task_count": 140, "domain_counts": DOMAINS,
                  "api_calls_by_preparation": 0, "originals_modified": False,
                  "gold_modified": False, "source_file_sha256": sources,
                  "online_input_files": "Only each public_file and chart_file; catalog metadata and all offline files are not prompt content.",
                  "public_task_keys": sorted(PUBLIC_KEYS)})
    files["preparation_audit.json"] = encoded(audit)
    files["catalog.json"] = encoded(catalog)
    return catalog, audit, files


def prepare_catalog(source_raw=DEFAULT_SOURCE, output=HERE):
    source_raw, output = Path(source_raw).resolve(), Path(output).resolve()
    if source_raw == output or source_raw in output.parents or output in source_raw.parents:
        raise ValueError("Output must be separate from the original snapshot")
    catalog, audit, files = compile_bundle(source_raw)
    # Check every existing destination before creating any missing file. Never
    # silently replace a prepared image, public record, offline record or audit.
    for relative, content in files.items():
        path = output / relative
        if path.exists() and (not path.is_file() or path.read_bytes() != content):
            raise ValueError("Refusing to change existing prepared data: " + str(path))
    for source, expected_hash in audit["source_file_sha256"].items():
        if digest(Path(source).read_bytes()) != expected_hash:
            raise ValueError("Source changed during preparation: " + source)
    for relative, content in files.items():
        path = output / relative
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as handle:
                handle.write(content)
    return catalog


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-raw", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=HERE)
    args = parser.parse_args()
    catalog = prepare_catalog(args.source_raw, args.output)
    print(json.dumps({"base_task_count": catalog["base_task_count"],
                      "condition": catalog["condition"], "output": str(args.output.resolve()),
                      "api_calls": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
