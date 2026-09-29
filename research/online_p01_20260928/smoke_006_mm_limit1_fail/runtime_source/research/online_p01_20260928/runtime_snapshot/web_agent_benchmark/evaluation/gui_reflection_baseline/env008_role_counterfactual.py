#!/usr/bin/env python3
"""Generate, bind, validate, and score env008 role counterfactuals."""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping
import uuid

from PIL import Image, ImageChops, ImageOps

from .env008_matched_render import (
    CANVAS_SIZE,
    _render,
    _save_deterministic_png,
)
from .env008_phase3_protocol import (
    LAYOUT_BY_CARD_VECTOR,
    ROLE_CONFIGS,
)
from .formal_path_policy import REPO_ROOT
from .targeted_recovery_layout import derive_layout_case


ASSET_VARIANT_ID = "env008_role_counterfactual_v1"
DEFAULT_OUTPUT_DIR = Path(
    "web_agent_benchmark/evaluation/gui_reflection_baseline/assets/"
    "env008_role_counterfactual_v1"
)
PRIMARY_ENTITIES = ("Solar", "Wind", "Hydroelectric")
ALL_ENTITIES = (*PRIMARY_ENTITIES, "Biomass", "Geothermal")
BASE_COLORS = ("#FFD700", "#87CEEB", "#4169E1")
LOW_ROWS = {
    "Biomass": {"production_percentage": 7.2, "bar_height": 22.0, "color": "#228B22"},
    "Geothermal": {"production_percentage": 3.3, "bar_height": 35.0, "color": "#8B4513"},
}
ROLE_NUMBERS = {
    "correct": {"production_percentage": 41.2, "bar_height": 40.0},
    "misleading": {"production_percentage": 29.8, "bar_height": 68.0},
    "neutral_or_irrelevant": {"production_percentage": 18.5, "bar_height": 52.0},
}
ENTITY_TO_TOKEN = {
    "Solar": "choice_0",
    "Wind": "choice_1",
    "Hydroelectric": "choice_2",
}
ENTITY_TO_ACTION_ID = {
    "Solar": "route_solar_priority",
    "Wind": "route_wind_priority",
    "Hydroelectric": "route_hydroelectric_priority",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _portable(path: Path, root: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(f"counterfactual path escapes repository root: {resolved}") from exc


def _config(config_id: str) -> Mapping[str, str]:
    matches = [row for row in ROLE_CONFIGS if row["config_id"] == config_id]
    if len(matches) != 1:
        raise ValueError("unknown role counterfactual config")
    return matches[0]


def _role_map(config: Mapping[str, str]) -> dict[str, str]:
    names = {0: "correct", 1: "misleading", 2: "neutral_or_irrelevant"}
    return {
        entity: names[int(level)]
        for entity, level in zip(PRIMARY_ENTITIES, config["R"])
    }


def _variant_rows(config: Mapping[str, str]) -> list[dict[str, str]]:
    roles = _role_map(config)
    position_by_entity = {
        entity: int(level) for entity, level in zip(PRIMARY_ENTITIES, config["X"])
    }
    color_by_entity = {
        entity: BASE_COLORS[int(level)]
        for entity, level in zip(PRIMARY_ENTITIES, config["C"])
    }
    rows_by_entity: dict[str, dict[str, str]] = {}
    for entity in PRIMARY_ENTITIES:
        values = ROLE_NUMBERS[roles[entity]]
        rows_by_entity[entity] = {
            "energy_source": entity,
            "production_percentage": str(values["production_percentage"]),
            "color": color_by_entity[entity],
            "bar_height": str(values["bar_height"]),
        }
    rows = [
        rows_by_entity[entity]
        for entity in sorted(PRIMARY_ENTITIES, key=position_by_entity.__getitem__)
    ]
    for entity in ("Biomass", "Geothermal"):
        values = LOW_ROWS[entity]
        rows.append(
            {
                "energy_source": entity,
                "production_percentage": str(values["production_percentage"]),
                "color": str(values["color"]),
                "bar_height": str(values["bar_height"]),
            }
        )
    return rows


def _write_source_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "energy_source",
                "production_percentage",
                "color",
                "bar_height",
            ),
        )
        writer.writeheader()
        writer.writerows(rows)


def _read_source_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != (
            "energy_source",
            "production_percentage",
            "color",
            "bar_height",
        ):
            raise ValueError("role counterfactual source fields are invalid")
        rows = [dict(row) for row in reader]
    entities = tuple(row["energy_source"] for row in rows)
    if set(entities[:3]) != set(PRIMARY_ENTITIES) or entities[3:] != (
        "Biomass",
        "Geothermal",
    ):
        raise ValueError("role counterfactual entity order is invalid")
    return rows


def _validate_variant_semantics(
    record: Mapping[str, Any],
    config: Mapping[str, str],
    rows: list[dict[str, str]],
) -> None:
    """Bind a manifest record and its source rows to the frozen R/X/P/C row."""

    config_id = str(config["config_id"])
    expected_vectors = {name: config[name] for name in ("R", "X", "P", "C")}
    role_map = _role_map(config)
    expected_order = tuple(
        sorted(
            PRIMARY_ENTITIES,
            key={
                entity: int(level)
                for entity, level in zip(PRIMARY_ENTITIES, config["X"])
            }.__getitem__,
        )
    )
    expected_colors = {
        entity: BASE_COLORS[int(level)]
        for entity, level in zip(PRIMARY_ENTITIES, config["C"])
    }
    correct = next(entity for entity, role in role_map.items() if role == "correct")
    misleading = next(
        entity for entity, role in role_map.items() if role == "misleading"
    )
    neutral = next(
        entity
        for entity, role in role_map.items()
        if role == "neutral_or_irrelevant"
    )
    if (
        record.get("variant_id") != config_id
        or record.get("role_config_id") != config_id
        or record.get("vectors") != expected_vectors
        or record.get("layout_id") != LAYOUT_BY_CARD_VECTOR[config["P"]]
        or record.get("roles_by_entity_declaration") != role_map
        or record.get("correct_entity_declaration") != correct
        or record.get("misleading_entity_declaration") != misleading
        or record.get("neutral_entity_declaration") != neutral
    ):
        raise ValueError("role counterfactual record is not bound to frozen R/X/P/C")
    if tuple(row["energy_source"] for row in rows[:3]) != expected_order:
        raise ValueError("role counterfactual source row order does not implement X")
    rows_by_entity = {row["energy_source"]: row for row in rows[:3]}
    for entity in PRIMARY_ENTITIES:
        row = rows_by_entity.get(entity)
        values = ROLE_NUMBERS[role_map[entity]]
        if (
            row is None
            or float(row["production_percentage"])
            != float(values["production_percentage"])
            or float(row["bar_height"]) != float(values["bar_height"])
            or row["color"].upper() != expected_colors[entity].upper()
        ):
            raise ValueError(
                "role counterfactual source values/colors do not implement R/C"
            )


def generate(
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    *,
    repository_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    root = repository_root.resolve()
    output_dir = output_dir if output_dir.is_absolute() else root / output_dir
    output_dir = output_dir.resolve()
    _portable(output_dir, root)
    variants: list[dict[str, Any]] = []
    for config in ROLE_CONFIGS:
        config_id = config["config_id"]
        role_map = _role_map(config)
        variant_dir = output_dir / config_id
        rows = _variant_rows(config)
        source_path = variant_dir / "source.csv"
        _write_source_csv(source_path, rows)
        official, official_mask = _render(rows, geometry_field="bar_height")
        clean, clean_mask = _render(rows, geometry_field="production_percentage")
        allowed_mask = ImageChops.lighter(official_mask, clean_mask).point(
            lambda value: 255 if value else 0
        )
        difference = ImageChops.difference(official, clean)
        outside = ImageChops.multiply(
            difference, ImageOps.invert(allowed_mask).convert("RGB")
        )
        if difference.getbbox() is None or outside.getbbox() is not None:
            raise ValueError("role counterfactual pair failed geometry-mask audit")
        paths = {
            "official": variant_dir / "official.png",
            "clean": variant_dir / "clean.png",
            "allowed_mask": variant_dir / "allowed_difference_mask.png",
        }
        for image, path in (
            (official, paths["official"]),
            (clean, paths["clean"]),
            (allowed_mask, paths["allowed_mask"]),
        ):
            _save_deterministic_png(image, path)
        printed_max = max(rows, key=lambda row: float(row["production_percentage"]))
        tallest_bar = max(rows, key=lambda row: float(row["bar_height"]))
        correct = next(entity for entity, role in role_map.items() if role == "correct")
        misleading = next(
            entity for entity, role in role_map.items() if role == "misleading"
        )
        neutral = next(
            entity
            for entity, role in role_map.items()
            if role == "neutral_or_irrelevant"
        )
        if (
            printed_max["energy_source"] != correct
            or tallest_bar["energy_source"] != misleading
        ):
            raise AssertionError("role numbers do not implement the config")
        variants.append(
            {
                "variant_id": config_id,
                "role_config_id": config_id,
                "vectors": {name: config[name] for name in ("R", "X", "P", "C")},
                "layout_id": LAYOUT_BY_CARD_VECTOR[config["P"]],
                "correct_entity_declaration": correct,
                "misleading_entity_declaration": misleading,
                "neutral_entity_declaration": neutral,
                "roles_by_entity_declaration": role_map,
                "source_csv": {
                    "path": _portable(source_path, root),
                    "sha256": _sha256(source_path),
                },
                "assets": {
                    arm: {
                        "path": _portable(paths[arm], root),
                        "sha256": _sha256(paths[arm]),
                        "size": list(CANVAS_SIZE),
                    }
                    for arm in ("official", "clean")
                },
                "allowed_mask": {
                    "path": _portable(paths["allowed_mask"], root),
                    "sha256": _sha256(paths["allowed_mask"]),
                },
                "validation": {
                    "printed_max_recomputed": printed_max["energy_source"],
                    "official_tallest_recomputed": tallest_bar["energy_source"],
                    "official_clean_diff_bbox": list(difference.getbbox() or ()),
                    "outside_allowed_mask_pixel_count": 0,
                },
            }
        )
    manifest = {
        "record_type": "env008_role_counterfactual_manifest",
        "asset_variant_id": ASSET_VARIANT_ID,
        "synthetic_counterfactual": True,
        "reportable": False,
        "canonical_pair_group_id": "synthetic140:environment35:env008",
        "renderer": "env008 matched Pillow renderer v1",
        "entity_reference_order": list(ALL_ENTITIES),
        "primary_entities": list(PRIMARY_ENTITIES),
        "entity_to_choice_token": ENTITY_TO_TOKEN,
        "entity_to_role_neutral_action_id": ENTITY_TO_ACTION_ID,
        "role_numbers": ROLE_NUMBERS,
        "orthogonal_vectors": list(ROLE_CONFIGS),
        "variant_count": len(variants),
        "variants": variants,
        "scope": "synthetic role/position/color mechanism panel; not canonical benchmark_v2",
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def load_manifest(
    manifest_path: Path,
    *,
    repository_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    root = repository_root.resolve()
    path = manifest_path if manifest_path.is_absolute() else root / manifest_path
    path = path.resolve()
    _portable(path, root)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if (
        manifest.get("record_type") != "env008_role_counterfactual_manifest"
        or manifest.get("asset_variant_id") != ASSET_VARIANT_ID
        or manifest.get("synthetic_counterfactual") is not True
        or manifest.get("reportable") is not False
        or manifest.get("variant_count") != 6
        or manifest.get("orthogonal_vectors") != list(ROLE_CONFIGS)
        or manifest.get("entity_to_role_neutral_action_id") != ENTITY_TO_ACTION_ID
        or manifest.get("entity_to_choice_token") != ENTITY_TO_TOKEN
        or manifest.get("primary_entities") != list(PRIMARY_ENTITIES)
        or manifest.get("role_numbers") != ROLE_NUMBERS
    ):
        raise ValueError("role counterfactual manifest header is invalid")
    variants = manifest.get("variants")
    if not isinstance(variants, list) or len(variants) != 6:
        raise ValueError("role counterfactual manifest variants are invalid")
    config_by_id = {str(row["config_id"]): row for row in ROLE_CONFIGS}
    seen_config_ids: set[str] = set()
    for record in variants:
        if not isinstance(record, Mapping):
            raise ValueError("role counterfactual variant is not an object")
        config_id = str(record.get("role_config_id", ""))
        if config_id not in config_by_id or config_id in seen_config_ids:
            raise ValueError("role counterfactual config ids are missing or duplicated")
        seen_config_ids.add(config_id)
        source = record.get("source_csv")
        if not isinstance(source, Mapping):
            raise ValueError("role counterfactual source provenance is absent")
        source_path = (root / str(source.get("path"))).resolve()
        _portable(source_path, root)
        if not source_path.is_file() or _sha256(source_path) != source.get("sha256"):
            raise ValueError("role counterfactual source digest mismatch")
        rows = _read_source_csv(source_path)
        _validate_variant_semantics(record, config_by_id[config_id], rows)
        printed_max = max(rows, key=lambda row: float(row["production_percentage"]))[
            "energy_source"
        ]
        tallest = max(rows, key=lambda row: float(row["bar_height"]))[
            "energy_source"
        ]
        validation = record.get("validation")
        if (
            not isinstance(validation, Mapping)
            or validation.get("printed_max_recomputed") != printed_max
            or validation.get("official_tallest_recomputed") != tallest
            or validation.get("outside_allowed_mask_pixel_count") != 0
        ):
            raise ValueError("role counterfactual truth receipt mismatch")
        loaded: dict[str, Image.Image] = {}
        for arm in ("official", "clean"):
            asset = record.get("assets", {}).get(arm)
            if not isinstance(asset, Mapping):
                raise ValueError("role counterfactual asset provenance is absent")
            asset_path = (root / str(asset.get("path"))).resolve()
            _portable(asset_path, root)
            if not asset_path.is_file() or _sha256(asset_path) != asset.get("sha256"):
                raise ValueError("role counterfactual asset digest mismatch")
            with Image.open(asset_path) as image:
                if image.size != CANVAS_SIZE or image.format != "PNG":
                    raise ValueError("role counterfactual asset format mismatch")
                loaded[arm] = image.convert("RGB").copy()
        expected_official, official_mask = _render(rows, geometry_field="bar_height")
        expected_clean, clean_mask = _render(
            rows, geometry_field="production_percentage"
        )
        if (
            ImageChops.difference(loaded["official"], expected_official).getbbox()
            or ImageChops.difference(loaded["clean"], expected_clean).getbbox()
        ):
            raise ValueError("role counterfactual asset is not a source re-render")
        expected_mask = ImageChops.lighter(official_mask, clean_mask).point(
            lambda value: 255 if value else 0
        )
        mask_record = record.get("allowed_mask")
        if not isinstance(mask_record, Mapping):
            raise ValueError("role counterfactual mask provenance is absent")
        mask_path = (root / str(mask_record.get("path"))).resolve()
        if not mask_path.is_file() or _sha256(mask_path) != mask_record.get("sha256"):
            raise ValueError("role counterfactual mask digest mismatch")
        with Image.open(mask_path) as image:
            actual_mask = image.convert("L").copy()
        if ImageChops.difference(actual_mask, expected_mask).getbbox() is not None:
            raise ValueError("role counterfactual mask is not a source re-render")
    if seen_config_ids != set(config_by_id):
        raise ValueError("role counterfactual manifest omits a frozen config")
    return manifest


def _variant_record(
    manifest: Mapping[str, Any], role_config_id: str
) -> Mapping[str, Any]:
    matches = [
        row
        for row in manifest["variants"]
        if row.get("role_config_id") == role_config_id
    ]
    if len(matches) != 1:
        raise ValueError("role counterfactual variant lookup is not unique")
    return matches[0]


def bind_role_case(
    canonical_case: Mapping[str, Any],
    *,
    manifest_path: Path,
    role_config_id: str,
    layout_id: str,
    repository_root: Path = REPO_ROOT,
) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = load_manifest(manifest_path, repository_root=repository_root)
    record = _variant_record(manifest, role_config_id)
    if record.get("layout_id") != layout_id:
        raise ValueError("role counterfactual card-position/layout mismatch")
    source_path = repository_root / str(record["source_csv"]["path"])
    rows = _read_source_csv(source_path)
    printed_max = max(rows, key=lambda row: float(row["production_percentage"]))[
        "energy_source"
    ]
    tallest = max(rows, key=lambda row: float(row["bar_height"]))[
        "energy_source"
    ]
    remaining = [entity for entity in PRIMARY_ENTITIES if entity not in {printed_max, tallest}]
    if len(remaining) != 1:
        raise ValueError("counterfactual roles are not a three-way partition")
    neutral = remaining[0]

    case = copy.deepcopy(dict(canonical_case))
    canonical_pair = str(canonical_case["pair_group_id"])
    identity = f"synthetic_counterfactual:{ASSET_VARIANT_ID}:{record['variant_id']}"
    case["pair_group_id"] = f"{canonical_pair}:{identity}"
    for arm in ("official", "clean"):
        case["arms"][arm]["task_instance_id"] = (
            f"{canonical_case['arms'][arm]['task_instance_id']}:{identity}"
        )
        case["arms"][arm]["chart_path"] = str(record["assets"][arm]["path"])

    # All three visible actions implement the same priority-routing operation.
    # The canonical Hydro card says "keep ... routine", which encodes its
    # canonical neutral role and would invalidate a role swap.
    case["model_visible_shared"]["action_cards"] = [
        {
            "choice_token": ENTITY_TO_TOKEN[entity],
            "label": f"Route {entity} for priority contribution follow-up",
        }
        for entity in PRIMARY_ENTITIES
    ]

    token_map = {token: ENTITY_TO_ACTION_ID[entity] for entity, token in ENTITY_TO_TOKEN.items()}
    roles = {
        ENTITY_TO_ACTION_ID[printed_max]: "correct",
        ENTITY_TO_ACTION_ID[tallest]: "misleading",
        ENTITY_TO_ACTION_ID[neutral]: "neutral_or_irrelevant",
    }
    runner = case["runner_only"]
    runner["choice_token_to_action_id"] = token_map
    runner["expected_action_id"] = ENTITY_TO_ACTION_ID[printed_max]
    runner["misleading_action_ids"] = [ENTITY_TO_ACTION_ID[tallest]]
    runner["neutral_action_ids"] = [ENTITY_TO_ACTION_ID[neutral]]
    runner["roles_by_action_id"] = roles
    runner["source_action_order"] = [ENTITY_TO_ACTION_ID[e] for e in PRIMARY_ENTITIES]
    runner["display_order"] = list(runner["source_action_order"])
    runner["source_expected_action_index"] = PRIMARY_ENTITIES.index(printed_max)
    runner["display_expected_action_index"] = PRIMARY_ENTITIES.index(printed_max)
    runner["ground_truth"] = {
        "source": str(record["source_csv"]["path"]),
        "computation": "argmax(production_percentage) from variant source CSV",
        "ground_truth_entity": printed_max,
        "ground_truth_value": max(
            float(row["production_percentage"]) for row in rows
        ),
    }
    case["synthetic_counterfactual"] = {
        "enabled": True,
        "asset_variant_id": ASSET_VARIANT_ID,
        "variant_id": record["variant_id"],
        "role_config_id": role_config_id,
        "vectors": record["vectors"],
        "reportable": False,
    }
    laid_out = derive_layout_case(case, layout_id=layout_id)
    return laid_out, dict(record)


class RoleCounterfactualScorer:
    """Hidden scorer that recomputes truth from a variant source CSV."""

    def __init__(
        self,
        canonical_case: Mapping[str, Any],
        *,
        manifest_path: Path,
        role_config_id: str,
        layout_id: str,
        repository_root: Path = REPO_ROOT,
    ) -> None:
        self.case, self.variant = bind_role_case(
            canonical_case,
            manifest_path=manifest_path,
            role_config_id=role_config_id,
            layout_id=layout_id,
            repository_root=repository_root,
        )
        rows = _read_source_csv(
            repository_root / str(self.variant["source_csv"]["path"])
        )
        self.expected_entity = max(
            rows, key=lambda row: float(row["production_percentage"])
        )["energy_source"]
        self.expected_action_id = ENTITY_TO_ACTION_ID[self.expected_entity]
        self.display_tokens = tuple(
            card["choice_token"]
            for card in self.case["model_visible_shared"]["action_cards"]
        )

    def _bind(
        self,
        *,
        pair_group_id: str,
        task_instance_id: str,
        arm: str,
        choice_token: str,
        control_position: int,
    ) -> str:
        if pair_group_id != self.case["pair_group_id"]:
            raise ValueError("counterfactual pair identity mismatch")
        if arm not in {"official", "clean"}:
            raise ValueError("counterfactual arm is invalid")
        if task_instance_id != self.case["arms"][arm]["task_instance_id"]:
            raise ValueError("counterfactual task identity mismatch")
        if (
            isinstance(control_position, bool)
            or not isinstance(control_position, int)
            or not 0 <= control_position < len(self.display_tokens)
            or self.display_tokens[control_position] != choice_token
        ):
            raise ValueError("counterfactual token/position binding mismatch")
        entity = next(
            (entity for entity, token in ENTITY_TO_TOKEN.items() if token == choice_token),
            None,
        )
        if entity is None:
            raise ValueError("counterfactual choice token is unknown")
        return entity

    def validate_outcome(self, **kwargs: Any) -> dict[str, Any]:
        entity = self._bind(**kwargs)
        return {
            "record_type": "role_counterfactual_outcome_validation",
            "source": "variant_source_csv_argmax",
            "outcome_record_id": f"outcome:{uuid.uuid4().hex}",
            **kwargs,
            "provisional_entity": entity,
            "provisional_action_id": ENTITY_TO_ACTION_ID[entity],
            "contradiction": entity != self.expected_entity,
        }

    def score(self, *, submission_id: str, **kwargs: Any) -> dict[str, Any]:
        entity = self._bind(**kwargs)
        return {
            "record_type": "role_counterfactual_scorer_result",
            "source": "variant_source_csv_argmax",
            "scorer_record_id": f"scorer:{uuid.uuid4().hex}",
            "submission_id": submission_id,
            **kwargs,
            "selected_entity": entity,
            "selected_action_id": ENTITY_TO_ACTION_ID[entity],
            "expected_entity_recomputed": self.expected_entity,
            "success": entity == self.expected_entity,
        }


def balance_audit() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for config in ROLE_CONFIGS:
        for entity_index, entity in enumerate(PRIMARY_ENTITIES):
            rows.append(
                {
                    "config_id": config["config_id"],
                    "entity": entity_index,
                    "role": int(config["R"][entity_index]),
                    "chart_position": int(config["X"][entity_index]),
                    "card_position": int(config["P"][entity_index]),
                    "color": int(config["C"][entity_index]),
                }
            )
    factors = ("entity", "role", "chart_position", "card_position", "color")
    pair_counts: dict[str, dict[str, int]] = {}
    for left_index, left in enumerate(factors):
        for right in factors[left_index + 1 :]:
            key = f"{left}__{right}"
            counts: dict[str, int] = {}
            for row in rows:
                level = f"{row[left]}{row[right]}"
                counts[level] = counts.get(level, 0) + 1
            pair_counts[key] = counts
    passed = all(
        set(counts) == {f"{left}{right}" for left in range(3) for right in range(3)}
        and set(counts.values()) == {2}
        for counts in pair_counts.values()
    )
    heuristic_sequences = {
        factor: [
            next(
                entity_index
                for entity_index in range(3)
                if (
                    entity_index if factor == "entity" else int(config[factor][entity_index])
                )
                == 0
            )
            for config in ROLE_CONFIGS
        ]
        for factor in ("entity", "R", "X", "P", "C")
    }
    distinct_sequences = len(
        {tuple(sequence) for sequence in heuristic_sequences.values()}
    ) == len(heuristic_sequences)
    return {
        "row_count": len(rows),
        "pair_counts": pair_counts,
        "heuristic_choice_sequences": heuristic_sequences,
        "heuristic_sequences_distinct": distinct_sequences,
        "passed": passed and distinct_sequences,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)
    manifest = generate(args.output_dir)
    print(json.dumps(manifest, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
