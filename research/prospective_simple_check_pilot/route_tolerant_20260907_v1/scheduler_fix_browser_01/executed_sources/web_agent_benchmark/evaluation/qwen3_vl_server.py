#!/usr/bin/env python3
"""Small local HTTP server for Qwen3-VL vision completions.

Run this with the Qwen3-VL conda environment, not the benchmark runner env.
The benchmark runner sends browser screenshots and prompts to this service.
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
    "max_pixels": None,
}
SERVER_PROTOCOL_VERSION = "2.0-native-multi-image"


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def load_qwen_model(model_path: Path, *, model_size: str, max_pixels: int) -> None:
    import torch
    from transformers import AutoProcessor, Qwen3VLForConditionalGeneration

    started = time.time()
    print(f"[qwen3_vl_server] Loading {model_size} from {model_path}", flush=True)
    print(f"[qwen3_vl_server] CUDA_VISIBLE_DEVICES={os.environ.get('CUDA_VISIBLE_DEVICES')}", flush=True)
    print(f"[qwen3_vl_server] torch.cuda.device_count={torch.cuda.device_count()}", flush=True)

    model = Qwen3VLForConditionalGeneration.from_pretrained(
        str(model_path),
        torch_dtype=torch.bfloat16,
        device_map="auto",
        low_cpu_mem_usage=True,
    )
    model.eval()
    processor = AutoProcessor.from_pretrained(
        str(model_path),
        min_pixels=256 * 28 * 28,
        max_pixels=max_pixels,
    )
    SERVER_STATE.update(
        {
            "model": model,
            "processor": processor,
            "model_path": str(model_path),
            "model_size": model_size,
            "started_at": time.time(),
            "max_pixels": max_pixels,
            "load_seconds": round(time.time() - started, 3),
        }
    )
    print(f"[qwen3_vl_server] Loaded in {SERVER_STATE['load_seconds']}s", flush=True)


def complete(payload: dict[str, Any]) -> dict[str, Any]:
    import torch
    from PIL import Image
    from qwen_vl_utils import process_vision_info

    model = SERVER_STATE["model"]
    processor = SERVER_STATE["processor"]
    if model is None or processor is None:
        raise RuntimeError("Qwen3-VL model is not loaded.")

    raw_paths = payload.get("image_paths")
    if raw_paths is None:
        raw_paths = [payload["image_path"]]
    if not isinstance(raw_paths, list) or not raw_paths:
        raise ValueError("image_paths must be a non-empty list")
    image_paths = [Path(value) for value in raw_paths]
    for image_path in image_paths:
        if not image_path.exists():
            raise FileNotFoundError(f"Image path does not exist: {image_path}")

    seed = payload.get("seed")
    generation_config = dict(payload.get("generation_config") or {})
    if seed is not None:
        torch.manual_seed(int(seed))
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(int(seed))

    images = [Image.open(path).convert("RGB") for path in image_paths]
    original_image_sizes = [list(image.size) for image in images]
    user_content: list[dict[str, Any]] = []
    for index, image in enumerate(images, start=1):
        # Keep each label adjacent to its image instead of relying on a
        # filename or a separately concatenated low-resolution contact sheet.
        user_content.extend(
            [
                {"type": "text", "text": f"Panel {index}:"},
                {"type": "image", "image": image},
            ]
        )
    user_content.append(
        {"type": "text", "text": str(payload.get("user_text", ""))}
    )
    messages = [
        {"role": "system", "content": str(payload.get("system_prompt", ""))},
        {
            "role": "user",
            "content": user_content,
        },
    ]
    try:
        text = processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        image_inputs, video_inputs = process_vision_info(messages)
        inputs = processor(
            text=[text],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
        )
        inputs = inputs.to(model.device)
    finally:
        for image in images:
            image.close()

    generate_kwargs: dict[str, Any] = {
        "max_new_tokens": int(payload.get("max_output_tokens") or 1024),
        "do_sample": bool(generation_config.get("do_sample", False)),
    }
    for key in ("temperature", "top_p", "top_k", "repetition_penalty"):
        if generation_config.get(key) is not None:
            generate_kwargs[key] = generation_config[key]

    started = time.time()
    with torch.inference_mode():
        generated_ids = model.generate(**inputs, **generate_kwargs)
    output_ids = generated_ids[:, inputs.input_ids.shape[1] :]
    output_text = processor.batch_decode(
        output_ids,
        skip_special_tokens=True,
        clean_up_tokenization_spaces=False,
    )[0].strip()
    return {
        "output_text": output_text,
        "model_path": SERVER_STATE["model_path"],
        "model_size": SERVER_STATE["model_size"],
        "generation_config": generate_kwargs,
        "input_token_count": int(inputs.input_ids.shape[1]),
        "output_token_count": int(output_ids.shape[1]),
        "input_image_count": len(image_paths),
        "original_image_sizes": original_image_sizes,
        "max_pixels_per_image": SERVER_STATE["max_pixels"],
        "server_protocol_version": SERVER_PROTOCOL_VERSION,
        "elapsed_seconds": round(time.time() - started, 3),
    }


class QwenHandler(BaseHTTPRequestHandler):
    server_version = "Qwen3VLHTTP/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[qwen3_vl_server] {self.address_string()} - {fmt % args}", flush=True)

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
                "max_pixels": SERVER_STATE["max_pixels"],
                "load_seconds": SERVER_STATE.get("load_seconds"),
                "native_multi_image": True,
                "server_protocol_version": SERVER_PROTOCOL_VERSION,
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
    parser.add_argument("--port", type=int, default=8045)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--model-size", choices=["8b", "32b"], required=True)
    parser.add_argument("--max-pixels", type=int, default=1280 * 28 * 28)
    args = parser.parse_args()

    if not args.model_path.exists():
        print(f"Model path does not exist: {args.model_path}", file=sys.stderr)
        return 2
    load_qwen_model(args.model_path, model_size=args.model_size, max_pixels=args.max_pixels)
    httpd = ThreadingHTTPServer((args.host, args.port), QwenHandler)
    print(f"[qwen3_vl_server] Listening on http://{args.host}:{args.port}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
