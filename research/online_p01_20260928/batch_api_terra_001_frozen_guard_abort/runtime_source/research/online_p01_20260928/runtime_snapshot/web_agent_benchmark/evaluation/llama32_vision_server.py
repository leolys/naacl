#!/usr/bin/env python3
"""Small local HTTP server for Llama-3.2 Vision completions.

Run this with the InternVL/Llama conda environment, not the benchmark runner
environment. The benchmark runner sends browser screenshots and prompts here.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


SERVER_STATE: dict[str, Any] = {
    "model": None,
    "processor": None,
    "model_path": None,
    "model_size": None,
    "started_at": None,
}


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def load_llama_model(model_path: Path, *, model_size: str) -> None:
    import torch
    from transformers import AutoProcessor, MllamaForConditionalGeneration

    started = time.time()
    print(f"[llama32_vision_server] Loading {model_size} from {model_path}", flush=True)
    print(
        f"[llama32_vision_server] CUDA_VISIBLE_DEVICES={os.environ.get('CUDA_VISIBLE_DEVICES')}",
        flush=True,
    )
    print(
        f"[llama32_vision_server] torch.cuda.device_count={torch.cuda.device_count()}",
        flush=True,
    )

    model = MllamaForConditionalGeneration.from_pretrained(
        str(model_path),
        torch_dtype=torch.bfloat16,
        device_map="auto",
        low_cpu_mem_usage=True,
    )
    model.eval()
    processor = AutoProcessor.from_pretrained(str(model_path))
    SERVER_STATE.update(
        {
            "model": model,
            "processor": processor,
            "model_path": str(model_path),
            "model_size": model_size,
            "started_at": time.time(),
            "load_seconds": round(time.time() - started, 3),
        }
    )
    print(f"[llama32_vision_server] Loaded in {SERVER_STATE['load_seconds']}s", flush=True)


def _build_manual_prompt(system_prompt: str, user_text: str) -> str:
    prompt_text = user_text
    if system_prompt.strip():
        prompt_text = f"{system_prompt.strip()}\n\n{user_text}"
    # Use manual Llama 3 chat tokens because these local processors may not
    # ship a chat_template. The older project script used the same manual
    # structure but with a non-special end marker; the canonical EOT token
    # helps generation stop after the JSON action.
    return (
        "<|begin_of_text|><|start_header_id|>user<|end_header_id|>\n\n"
        f"<|image|>{prompt_text}<|eot_id|>"
        "<|start_header_id|>assistant<|end_header_id|>\n\n"
    )


def complete(payload: dict[str, Any]) -> dict[str, Any]:
    import torch
    from PIL import Image
    from transformers import StoppingCriteria, StoppingCriteriaList

    model = SERVER_STATE["model"]
    processor = SERVER_STATE["processor"]
    if model is None or processor is None:
        raise RuntimeError("Llama-3.2 Vision model is not loaded.")

    image_path = Path(payload["image_path"])
    if not image_path.exists():
        raise FileNotFoundError(f"Image path does not exist: {image_path}")

    seed = payload.get("seed")
    generation_config = dict(payload.get("generation_config") or {})
    if seed is not None:
        torch.manual_seed(int(seed))
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(int(seed))

    image = Image.open(image_path).convert("RGB")
    input_text = _build_manual_prompt(
        str(payload.get("system_prompt", "")),
        str(payload.get("user_text", "")),
    )
    inputs = processor(images=image, text=input_text, return_tensors="pt").to(model.device)

    class FirstJsonObjectStopper(StoppingCriteria):
        def __init__(self, tokenizer: Any, prompt_len: int) -> None:
            self.tokenizer = tokenizer
            self.prompt_len = prompt_len

        def __call__(self, input_ids: Any, scores: Any, **kwargs: Any) -> bool:
            generated = input_ids[0][self.prompt_len :]
            if generated.numel() == 0:
                return False
            text = self.tokenizer.decode(
                generated,
                skip_special_tokens=True,
                clean_up_tokenization_spaces=False,
            )
            start = text.find("{")
            if start < 0:
                return False
            balance = 0
            in_string = False
            escaped = False
            for ch in text[start:]:
                if escaped:
                    escaped = False
                    continue
                if ch == "\\":
                    escaped = True
                    continue
                if ch == '"':
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if ch == "{":
                    balance += 1
                elif ch == "}":
                    balance -= 1
                    if balance == 0:
                        return True
            return False

    do_sample = bool(generation_config.get("do_sample", False))
    eos_ids = [processor.tokenizer.eos_token_id]
    eot_id = processor.tokenizer.convert_tokens_to_ids("<|eot_id|>")
    if isinstance(eot_id, int) and eot_id >= 0 and eot_id not in eos_ids:
        eos_ids.append(eot_id)
    generate_kwargs: dict[str, Any] = {
        "max_new_tokens": int(payload.get("max_output_tokens") or 1024),
        "do_sample": do_sample,
        "pad_token_id": processor.tokenizer.eos_token_id,
        "eos_token_id": eos_ids,
        "stopping_criteria": StoppingCriteriaList(
            [FirstJsonObjectStopper(processor.tokenizer, inputs.input_ids.shape[1])]
        ),
    }
    for key in ("temperature", "top_p", "top_k", "repetition_penalty"):
        if generation_config.get(key) is None:
            continue
        if key in {"temperature", "top_p", "top_k"} and not do_sample:
            continue
        generate_kwargs[key] = generation_config[key]

    started = time.time()
    with torch.inference_mode():
        generated_ids = model.generate(**inputs, **generate_kwargs)
    output_ids = generated_ids[:, inputs.input_ids.shape[1] :]
    output_text = processor.tokenizer.decode(
        output_ids[0],
        skip_special_tokens=True,
        clean_up_tokenization_spaces=False,
    ).strip()
    serializable_generation_config = {
        key: value
        for key, value in generate_kwargs.items()
        if key not in {"stopping_criteria"} and isinstance(value, (str, int, float, bool, list, type(None)))
    }
    return {
        "output_text": output_text,
        "model_path": SERVER_STATE["model_path"],
        "model_size": SERVER_STATE["model_size"],
        "generation_config": serializable_generation_config,
        "elapsed_seconds": round(time.time() - started, 3),
    }


class Llama32Handler(BaseHTTPRequestHandler):
    server_version = "Llama32VisionHTTP/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[llama32_vision_server] {self.address_string()} - {fmt % args}", flush=True)

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/health":
            _json_response(self, 404, {"ok": False, "error": "not_found"})
            return
        _json_response(
            self,
            200,
            {
                "ok": SERVER_STATE["model"] is not None,
                "model_path": SERVER_STATE["model_path"],
                "model_size": SERVER_STATE["model_size"],
                "load_seconds": SERVER_STATE.get("load_seconds"),
            },
        )

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/complete":
            _json_response(self, 404, {"ok": False, "error": "not_found"})
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
            result = complete(payload)
            _json_response(self, 200, {"ok": True, **result})
        except Exception as exc:
            _json_response(self, 500, {"ok": False, "error": repr(exc)})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8047)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--model-size", choices=["11b", "90b"], required=True)
    args = parser.parse_args()

    if not args.model_path.exists():
        print(f"Model path does not exist: {args.model_path}", file=sys.stderr)
        return 2
    load_llama_model(args.model_path, model_size=args.model_size)
    httpd = ThreadingHTTPServer((args.host, args.port), Llama32Handler)
    print(f"[llama32_vision_server] Listening on http://{args.host}:{args.port}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
