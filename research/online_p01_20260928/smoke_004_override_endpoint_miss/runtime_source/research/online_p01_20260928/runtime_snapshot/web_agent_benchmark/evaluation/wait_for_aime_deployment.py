#!/usr/bin/env python3
"""Wait for one frozen AIME deployment without permitting model-group fallback."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

import requests


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deployment", required=True)
    parser.add_argument("--base-url", default="https://aimemodeldev.myhexin.com/litellm/v1")
    parser.add_argument("--proxy", default="http://127.0.0.1:18890")
    parser.add_argument("--interval-sec", type=float, default=300)
    parser.add_argument("--max-wait-sec", type=float, default=21600)
    parser.add_argument("--request-timeout-sec", type=float, default=120)
    args = parser.parse_args()

    api_key = os.environ.get("AIME_LITELLM_API_KEY")
    if not api_key:
        print("AIME_LITELLM_API_KEY is required", file=sys.stderr)
        return 2

    deadline = time.monotonic() + args.max_wait_sec
    attempt = 0
    while True:
        attempt += 1
        status_code = None
        returned_model = None
        error = None
        try:
            response = requests.post(
                f"{args.base_url.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": args.deployment,
                    "messages": [{"role": "user", "content": "Reply exactly OK."}],
                    "max_tokens": 64,
                    "temperature": 0,
                    "top_p": 1,
                    "seed": 12345,
                },
                proxies={"http": args.proxy, "https": args.proxy},
                timeout=(20, args.request_timeout_sec),
            )
            status_code = response.status_code
            body = response.json() if response.text.strip() else {}
            returned_model = body.get("model")
            if response.status_code == 200:
                if returned_model != args.deployment:
                    print(json.dumps({
                        "timestamp": now(),
                        "attempt": attempt,
                        "status": "identity_mismatch",
                        "requested_deployment": args.deployment,
                        "response_model": returned_model,
                    }))
                    return 3
                print(json.dumps({
                    "timestamp": now(),
                    "attempt": attempt,
                    "status": "available",
                    "requested_deployment": args.deployment,
                    "response_model": returned_model,
                }))
                return 0
            error_payload = body.get("error")
            error = (
                error_payload.get("message")
                if isinstance(error_payload, dict)
                else str(error_payload or "")
            )
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"

        print(json.dumps({
            "timestamp": now(),
            "attempt": attempt,
            "status": "waiting",
            "status_code": status_code,
            "requested_deployment": args.deployment,
            "response_model": returned_model,
            "error_excerpt": str(error or "")[:240],
        }), flush=True)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return 4
        time.sleep(min(args.interval_sec, remaining))


if __name__ == "__main__":
    raise SystemExit(main())
