"""Native Chinese sidecars for NEW records; no API/network and no answer repair."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
OLD = HERE.parent / "obc140_20260923/terra140_native_zh_20260924"
sys.path.insert(0, str(OLD.parent))
import panel_core as core

_spec = importlib.util.spec_from_file_location("legacy_native_helpers", OLD / "native_zh.py")
legacy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(legacy)
sid = legacy.sid
items = legacy.items


def records():
    catalog = core.read(HERE / "prepared/catalog.json")
    for entry in catalog["tasks"]:
        slug = entry["task_slug"]
        path = HERE / "run/tasks" / slug / "record.json"
        record = core.read(path)
        if record is None:
            record = {"task_slug": slug, "domain": entry["domain"],
                "chart_file": str(HERE / "prepared" / entry["chart_file"]),
                "public_task": core.read(HERE / "prepared" / entry["public_file"]),
                "status": {p: "not_run" for p in core.PHASES}, "stages": {}, "translations": {"items": {}},
                "proposal": None, "generated": None, "normalized": None, "verification": None,
                "rule_state": [], "provenance": {"protocol": "runtime_dom_public_v1", "new_model_calls": 0}}
        # Only this new run's rejected/raw outputs; not previous batch chains.
        for phase in ("proposal", "generation", "verification"):
            folder = record.get("stages", {}).get(phase, {}).get("folder")
            if record["status"][phase] != "failed" or not folder:
                continue
            paths = sorted((path.parent / folder).glob("response_*.json"))
            if not paths:
                continue
            response = core.read(paths[-1])
            choices = response.get("choices", [])
            if not choices:
                continue
            answer = choices[0].get("message", {}).get("content")
            if isinstance(answer, str) and answer.strip():
                record.setdefault("display_failure_outputs", {})[phase] = answer
                record.setdefault("display_failure_provenance", {})[phase] = {
                    "response_file": str(paths[-1]), "sha256": core.digest(paths[-1]),
                    "finish_reason": choices[0].get("finish_reason"),
                    "scope": "this new run raw failed-stage output only; not repaired or accepted"}
        yield record


def old_exact_translations():
    translated, warnings, origins = legacy.load_translations()
    if warnings:
        raise ValueError("Old native translation cache has unresolved numeric warnings")
    text_by_id = {}
    for path in sorted((OLD / "translations/inbox").glob("chunk_*.json")):
        for row in core.read(path)["items"]:
            text_by_id[row["id"]] = row["text"]
    return {identity: {"en": text_by_id[identity], "zh": value,
                       "source": str(OLD / origins[identity])}
            for identity, value in translated.items()}


def seed_cache():
    dest = HERE / "translations/reused_exact_strings.json"
    if dest.exists():
        return core.read(dest)
    old, accepted = old_exact_translations(), {}
    for record in records():
        for row in items(record):
            identity = sid(row["text"])
            if identity in old and old[identity]["en"] == row["text"]:
                accepted[identity] = old[identity]
    core.dump(dest, {"scope": "translation-only exact string reuse; never old model answers or judgments",
                     "producer": "codex-native", "items": accepted})
    return core.read(dest)


def prepare(max_chars=11000):
    cache = seed_cache()
    assigned = {identity: item["en"] for identity, item in cache["items"].items()}
    inbox = HERE / "translations/inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    for path in sorted(inbox.glob("chunk_*.json")):
        for row in core.read(path)["items"]:
            assigned[row["id"]] = row["text"]
    pending = {}
    for record in records():
        for row in items(record):
            identity = sid(row["text"])
            if identity in assigned:
                if assigned[identity] != row["text"]:
                    raise ValueError("Translation key collision")
                continue
            pending.setdefault(identity, {"id": identity, "text": row["text"], "examples": []})
            if len(pending[identity]["examples"]) < 2:
                pending[identity]["examples"].append(record["task_slug"] + ":" + row["key"])
    chunks, current, length = [], [], 0
    for row in pending.values():
        if current and length + len(row["text"]) > max_chars:
            chunks.append(current)
            current, length = [], 0
        current.append(row)
        length += len(row["text"])
    if current:
        chunks.append(current)
    offset, written = len(list(inbox.glob("chunk_*.json"))), []
    for index, chunk in enumerate(chunks, offset + 1):
        path = inbox / ("chunk_%03d.json" % index)
        if path.exists():
            raise FileExistsError(path)
        core.dump(path, {"instruction": "Translate faithfully into simplified Chinese. Keep numbers, entities, quotes, negation, uncertainty, and mistakes. Do not repair or complete the model. Return items keyed by id with producer codex-native. No API calls.", "items": chunk})
        written.append({"file": path.name, "items": len(chunk)})
    return {"new_chunks": written, "new_strings": len(pending), "exact_translation_cache": len(cache["items"])}


def load_translations():
    cache = core.read(HERE / "translations/reused_exact_strings.json", {"items": {}})
    translated = {identity: row["zh"] for identity, row in cache["items"].items()}
    origin = {identity: row["source"] for identity, row in cache["items"].items()}
    warnings = []
    for path in sorted((HERE / "translations/outbox").glob("chunk_*.json")):
        source = core.read(HERE / "translations/inbox" / path.name)
        value = core.read(path)
        expected = {row["id"]: row["text"] for row in source["items"]}
        if value.get("producer") != "codex-native" or set(value.get("items", {})) != set(expected):
            raise ValueError("Translation key/producer mismatch: " + path.name)
        warnings.extend({"file": path.name, **row} for row in core.validate_translation(
            [{"key": key, "text": text} for key, text in expected.items()], value))
        for key, text in value["items"].items():
            if key in translated and translated[key] != text:
                raise ValueError("Conflicting translation")
            translated[key], origin[key] = text, str(path)
    return translated, warnings, origin


def status():
    translated, warnings, _ = load_translations()
    complete, missing = 0, set()
    for record in records():
        expected = {sid(row["text"]) for row in items(record)}
        complete += expected <= set(translated)
        missing.update(expected - set(translated))
    return {"tasks_current_text_complete": complete, "missing_unique_strings": len(missing),
            "native_unique_translations": len(translated), "numeric_warnings": warnings,
            "api_translation_calls": 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "status"])
    args = parser.parse_args()
    print(json.dumps(prepare() if args.command == "prepare" else status(), ensure_ascii=False))
