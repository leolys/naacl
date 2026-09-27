"""Offline audit of request isolation, checkpoint pairing, resumption, and costs."""
import argparse
import copy
import hashlib
import json
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def actor_url_normalized(payload):
    """Only normalize the parsed state.url, leaving all other prompt/image bytes."""
    result = copy.deepcopy(payload)
    text = result["messages"][1]["content"][0]["text"]
    before, tail = text.split("Current page state JSON:\n", 1)
    state_text, after = tail.split("\n\nAllowed actions:\n", 1)
    state = json.loads(state_text)
    old_url = state["url"]
    url = urlparse(old_url)
    if url.hostname != "127.0.0.1" or url.scheme != "http" or not url.port:
        raise ValueError("Not an ephemeral local browser origin")
    state["url"] = "http://127.0.0.1:EPHEMERAL" + url.path
    if url.query or url.fragment:
        raise ValueError("Unexpected query/fragment")
    result["messages"][1]["content"][0]["text"] = before + "Current page state JSON:\n" + json.dumps(state, ensure_ascii=False, indent=2) + "\n\nAllowed actions:\n" + after
    return result, old_url


def audit(root):
    root = Path(root)
    ledger = read(root / "ledger.json")
    summary = read(root / "summary.json")
    requests = [e for e in ledger["events"] if e["kind"] == "request"]
    reuses = [e for e in ledger["events"] if e["kind"] == "reused_response"]
    isolation, images = [], []
    markers = ("official140", "clean140", "misleader_type", "evaluation_hidden_from_agent", "ground_truth", "correct_action_id", "irrelevant_action_failure")
    for path in sorted(root.rglob("request.json")):
        payload = read(path)
        text_chunks = []
        num_images = 0
        for msg in payload["messages"]:
            if isinstance(msg["content"], str):
                text_chunks.append(msg["content"])
            else:
                for part in msg["content"]:
                    if part["type"] == "text":
                        text_chunks.append(part["text"])
                    elif part["type"] == "image_url":
                        num_images += 1
        visible_text = "\n".join(text_chunks)
        isolation.append({"request": str(path.relative_to(root)), "forbidden_marker_hits": [x for x in markers if x in visible_text], "image_count": num_images})
    reuse_checks = []
    for arm in ("official140", "clean140"):
        folder = root / arm / "prefix/actor_00"
        current = read(folder / "request.json")
        source = read(folder / "reused_source_request.json")
        normalized_current, current_url = actor_url_normalized(current)
        normalized_source, source_url = actor_url_normalized(source)
        reuse_checks.append({"arm": arm, "only_parsed_state_url_port_differs": normalized_current == normalized_source,
                             "original_url": source_url, "rebuilt_url": current_url,
                             "raw_payload_equal": current == source})
        checkpoint = read(root / arm / "checkpoint.json")
        reference = root / arm / "prefix" / Path(checkpoint["image"]).name
        expected = digest(reference)
        for path in sorted((root / arm).rglob("image_identity.json")):
            if path.parent.name in ("shared_initial", "questions", "supplement", "verification"):
                images.append({"stage": str(path.parent.relative_to(root)), "same_checkpoint_image": read(path)["sha256"] == expected})
    sources = []
    for path, expected in read(root / "source_hashes.json").items():
        rel = PurePosixPath(path).relative_to("/mnt/data/lys/CognitiveHijacking_CognitiveDenial")
        local = root / "runtime_source" / Path(str(rel))
        sources.append({"source": path, "snapshot_matches": local.is_file() and digest(local) == expected})
    outcomes = []
    for arm in summary["results"]:
        initial = arm.get("initial", {}).get("chains", [])
        for branch, result in arm["branches"].items():
            stages = result.get("stages", {})
            outcomes.append({"arm": arm["arm"], "branch": branch, "initial_chain_count": len(initial),
                "initial_option_labels": [c["C"]["option_label"] for c in initial],
                "questions": len(stages.get("questions", {}).get("questions", [])) if branch not in ("original_submit", "initial_only") else None,
                "new_chains": len(stages.get("supplement", {}).get("new_chains", [])) if branch not in ("original_submit", "initial_only") else None,
                "status": result["status"], "submitted": result.get("submitted"), "final_selection": result.get("final_selection"), "outcome": result.get("outcome"),
                "actual_selection_changes": sum(1 for e in result.get("continuation", []) if e["action"].get("action") == "select_option" and e.get("receipt", {}).get("executed") and e["action"].get("option_text") != e.get("selection_before"))})
    return {"request_attempts": ledger["request_attempts"], "request_events": len(requests),
            "reused_responses": len(reuses), "browser_operations": ledger["browser_operations"],
            "prompt_tokens": sum((e.get("usage") or {}).get("prompt_tokens", 0) for e in requests),
            "completion_tokens": sum((e.get("usage") or {}).get("completion_tokens", 0) for e in requests),
            "retries": sum(e["attempt"] > 1 for e in requests), "input_isolation": isolation,
            "resume_equivalence": reuse_checks, "method_image_identity": images,
            "source_snapshots": sources, "outcomes": outcomes,
            "limitations": "Marker/structural checks do not prove absence of every semantic leak. No model correctness judgment is automated here."}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.run)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps({k:v for k,v in result.items() if k not in ("input_isolation", "source_snapshots", "method_image_identity")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
