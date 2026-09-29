#!/usr/bin/env python3
"""Local actor endpoint proxy (declared infra difference).

Forwards OpenAI-compatible chat completions to the local vLLM server and
injects response_format json_object, approximating the structured-output
compliance of the original pilot's API actor. Payloads are otherwise
forwarded byte-identical; responses are forwarded byte-identical.
"""
import json
import sys

import requests as rq
from flask import Flask, Response, request

UP = "http://127.0.0.1:8058"
app = Flask(__name__)


@app.post("/v1/chat/completions")
def chat():
    body = request.get_json(force=True)
    body.setdefault("response_format", {"type": "json_object"})
    try:
        up = rq.post(UP + "/v1/chat/completions", json=body, timeout=(10, 900))
    except rq.RequestException as e:
        return Response(json.dumps({"error": {"message": "proxy_upstream_%s" % type(e).__name__,
                                              "type": "proxy_upstream_error"}}),
                        status=502, content_type="application/json")
    headers = {"Content-Type": up.headers.get("Content-Type", "application/json")}
    if "x-request-id" in up.headers:
        headers["x-request-id"] = up.headers["x-request-id"]
    return Response(up.content, status=up.status_code, headers=headers)


@app.get("/v1/models")
def models():
    r = rq.get(UP + "/v1/models", timeout=10)
    return Response(r.content, status=r.status_code, content_type=r.headers.get("Content-Type", "application/json"))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(sys.argv[1]) if len(sys.argv) > 1 else 8059, threaded=True)
