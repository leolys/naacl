"""Read-only metadata for the authorized gateway/model; never generate a completion.

Mask credentials at input, omit auth headers, retain only the requested model's
public capability/pricing fields. No fallback, retries, key creation or updates.
"""
import argparse
import getpass
import json
import os
import time
from pathlib import Path

import requests

from research.decision_evidence_audit.core import write_json
from .api_backend import redact


def selected_info(data, model):
    entries = data.get("data", []) if isinstance(data, dict) else []
    if not isinstance(entries, list):
        return []
    selected = []
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("model_name", entry.get("id")) != model:
            continue
        info = entry.get("model_info") or {}
        allowed = {k: v for k, v in info.items() if any(x in k for x in ("cost", "token", "vision", "mode", "reasoning"))}
        params = entry.get("litellm_params") or {}
        selected.append(dict(model_name=model, model_info=allowed,
                             configured_upstream_model=params.get("model")))
    return selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--model", default="gpt-5.6-sol")
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    token = os.environ.get("MODEL_API_KEY") or getpass.getpass("API Key (hidden): ").strip()
    if not token:
        raise SystemExit("missing credential; no requests")
    session = requests.Session()
    session.trust_env = False
    session.proxies = {"http": "http://127.0.0.1:18891", "https": "http://127.0.0.1:18891"}
    records = []
    try:
        for endpoint, params in (("/models", None), ("/model/info", {"model": args.model})):
            record = dict(endpoint=endpoint, params=params, method="GET", generation_calls=0)
            start = time.monotonic()
            records.append(record)
            write_json(root / "requests.json", records)
            try:
                response = session.get("https://aimemodeldev.myhexin.com/litellm" + endpoint,
                    params=params, headers={"Authorization": "Bearer " + token},
                    timeout=20, allow_redirects=False)
                record["http_status"] = response.status_code
                data = redact(response.json(), token)
                if response.status_code == 200:
                    record["top_level_keys"] = list(data) if isinstance(data, dict) else []
                    record["selected_model_info"] = selected_info(data, args.model)
                    if endpoint == "/models":
                        record["model_ids"] = [e.get("id") for e in data.get("data", []) if isinstance(e, dict)]
                        record["selected_id_present"] = args.model in record["model_ids"]
                else:
                    record["error"] = data.get("error", data.get("detail")) if isinstance(data, dict) else "non_object_response"
            except Exception as exc:
                record["error_type"] = type(exc).__name__
            finally:
                record["elapsed_seconds"] = round(time.monotonic() - start, 3)
                write_json(root / "requests.json", records)
                print(json.dumps({k: v for k, v in record.items() if k != "model_ids"}, ensure_ascii=False), flush=True)
            # A failed discovery/transport is not a reason to try more endpoints.
            if endpoint == "/models" and record.get("http_status") != 200:
                break
    finally:
        session.close()
    write_json(root / "summary.json", dict(metadata_get_attempts=len(records), real_generation_calls=0,
        selected_model=args.model, records=records, note="Gateway metadata claims, not independent weight or invoice attestation."))


if __name__ == "__main__":
    main()
