"""Serial loopback-only VLM adapter. Local weights only; no automatic retry/fallback.

InternVL tiling/chat construction follows the model-owned public inference code.
The existing actor and verifier prompts are passed unchanged to native templates.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import time
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer

from .settings import CONFIGS, GPU, PORT


def image_tiles(image, size=448, max_num=12):
    """Official InternVL dynamic tiling with an optional whole-image thumbnail."""
    width, height = image.size
    ratios = sorted({(i, j) for n in range(1, max_num + 1)
                     for i in range(1, n + 1) for j in range(1, n + 1)
                     if 1 <= i * j <= max_num}, key=lambda x: x[0] * x[1])
    best, diff = (1, 1), float('inf')
    for ratio in ratios:
        delta = abs(width / height - ratio[0] / ratio[1])
        if delta < diff or (delta == diff and width * height > .5 * size * size * ratio[0] * ratio[1]):
            best, diff = ratio, delta
    image_grid = image.resize((size * best[0], size * best[1]))
    tiles = [image_grid.crop(((i % best[0]) * size, (i // best[0]) * size,
                             ((i % best[0]) + 1) * size, ((i // best[0]) + 1) * size))
             for i in range(best[0] * best[1])]
    if len(tiles) > 1:
        tiles.append(image.resize((size, size)))
    return tiles


class Engine:
    def __init__(self, name, allowed_root):
        assert os.environ.get('CUDA_VISIBLE_DEVICES') == GPU, 'Only authorized physical GPU 7'
        import torch
        import transformers
        from transformers import AutoModel, AutoProcessor, AutoTokenizer
        assert torch.cuda.device_count() == 1, 'Exactly one visible GPU required'
        self.torch, self.config = torch, CONFIGS[name]
        self.allowed_root = Path(allowed_root).resolve(strict=True)
        path = Path(self.config['weights'])
        index = json.loads((path / 'model.safetensors.index.json').read_text())
        shards = sorted(set(index['weight_map'].values()))
        assert all((path / shard).is_file() for shard in shards)
        self.info = dict(model_name=name, display=self.config['display'], model_path=str(path),
            adapter='local_backbone_extension_v1', family=self.config['family'], native_multi_image=True,
            physical_gpu=GPU, dtype='bfloat16', quantization=None, cpu_offload=False,
            preprocessing=(dict(recipe='InternVL3 official dynamic tiling', tile_size=448,
                                max_tiles=12, thumbnail=True, normalize='ImageNet')
                           if self.config['family'] == 'internvl3' else
                           dict(recipe='qwen_vl_utils native image processing', min_pixels=200704, max_pixels=1003520)),
            decoding=dict(do_sample=False, max_new_tokens=1024, seed=12345),
            packages={p: importlib.metadata.version(p) for p in ('torch','transformers','accelerate','qwen-vl-utils','timm')},
            model_files={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in path.iterdir() if p.suffix in ('.json', '.py') and p.is_file()},
            weight_shards=[dict(name=s, bytes=(path / s).stat().st_size) for s in shards],
            weight_hash_note='config/index/code SHA256 and shard byte sizes; full weight SHA256 not computed')
        torch.manual_seed(12345)
        if self.config['family'] == 'internvl3':
            self.model = AutoModel.from_pretrained(str(path), torch_dtype=torch.bfloat16,
                low_cpu_mem_usage=True, trust_remote_code=True, local_files_only=True,
                device_map={'': 0}, use_flash_attn=False).eval()
            self.tokenizer = AutoTokenizer.from_pretrained(str(path), trust_remote_code=True,
                local_files_only=True, use_fast=False)
            self.info['attention'] = 'InternVL eager; use_flash_attn=False'
        else:
            cls = getattr(transformers, 'Qwen3VLForConditionalGeneration' if self.config['family'] == 'qwen3'
                          else 'Qwen2_5_VLForConditionalGeneration')
            self.model = cls.from_pretrained(str(path), torch_dtype=torch.bfloat16,
                device_map={'': 0}, local_files_only=True, attn_implementation='sdpa').eval()
            self.processor = AutoProcessor.from_pretrained(str(path), local_files_only=True,
                min_pixels=200704, max_pixels=1003520)
            self.info['attention'] = 'sdpa'
        generation_config = getattr(self.model, 'generation_config', None)
        if generation_config is None:
            generation_config = self.model.language_model.generation_config
        self.info['generation_config'] = generation_config.to_dict()
        self.info['loaded_parameter_count'] = sum(p.numel() for p in self.model.parameters())
        self.info['loaded_parameter_devices'] = sorted({str(p.device) for p in self.model.parameters()})
        if self.info['loaded_parameter_devices'] != ['cuda:0']:
            raise RuntimeError('Unexpected offload/device placement')
        self.info['peak_memory_allocated_bytes_at_load'] = torch.cuda.max_memory_allocated()
        print('MODEL_READY ' + json.dumps(self.info), flush=True)

    def complete(self, payload):
        from PIL import Image
        if set(payload) != {'system_prompt', 'user_prompt', 'image_paths'}:
            raise ValueError('Unexpected request fields')
        paths = [Path(p).resolve(strict=True) for p in payload['image_paths']]
        if not paths or len(paths) > 4 or any(not p.is_relative_to(self.allowed_root) for p in paths):
            raise ValueError('Images must be recorded observations under this run root')
        images = []
        for path in paths:
            with Image.open(path) as source:
                images.append(source.convert('RGB'))
        torch = self.torch
        torch.manual_seed(12345)
        start = time.monotonic()
        torch.cuda.reset_peak_memory_stats()
        with torch.inference_mode():
            if self.config['family'] == 'internvl3':
                text, prompt_tokens, output_tokens, vision = self.internvl(payload, images)
            else:
                text, prompt_tokens, output_tokens, vision = self.qwen(payload, paths)
        torch.cuda.synchronize()
        return dict(text=text, metadata=dict(model_name=self.info['model_name'],
            usage=dict(prompt_tokens=prompt_tokens, completion_tokens=output_tokens,
                       total_tokens=prompt_tokens + output_tokens),
            elapsed_seconds=time.monotonic() - start, vision=vision,
            original_image_sizes=[list(im.size) for im in images],
            image_sha256=[hashlib.sha256(p.read_bytes()).hexdigest() for p in paths],
            peak_memory_allocated_bytes=torch.cuda.max_memory_allocated(),
            decoding=self.info['decoding']))

    def qwen(self, payload, paths):
        from qwen_vl_utils import process_vision_info
        content = []
        for i, path in enumerate(paths):
            content.extend([dict(type='text', text=f'Panel {i+1}:'), dict(type='image', image=str(path))])
        content.append(dict(type='text', text=payload['user_prompt']))
        messages = [dict(role='system', content=payload['system_prompt']), dict(role='user', content=content)]
        rendered = self.processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        images, videos = process_vision_info(messages)
        inputs = self.processor(text=[rendered], images=images, videos=videos, padding=True, return_tensors='pt').to('cuda:0')
        outputs = self.model.generate(**inputs, max_new_tokens=1024, do_sample=False)
        n = inputs.input_ids.shape[-1]
        new = outputs[:, n:]
        text = self.processor.batch_decode(new, skip_special_tokens=True, clean_up_tokenization_spaces=False)[0]
        return text.strip(), int(n), int(new.shape[-1]), dict(
            image_grid_thw=inputs.image_grid_thw.cpu().tolist(),
            pixel_values_shape=list(inputs.pixel_values.shape), image_count=len(paths))

    def internvl(self, payload, images):
        import torchvision.transforms as T
        from torchvision.transforms.functional import InterpolationMode
        transform = T.Compose([T.Resize((448,448), interpolation=InterpolationMode.BICUBIC), T.ToTensor(),
                               T.Normalize(mean=(.485,.456,.406), std=(.229,.224,.225))])
        tiles = [image_tiles(im) for im in images]
        counts = [len(t) for t in tiles]
        pixels = self.torch.stack([transform(im) for group in tiles for im in group]).to(device='cuda:0', dtype=self.torch.bfloat16)
        # Follow local model.chat() exactly, but retain actual input/output token counts.
        get_template = sys.modules[type(self.model).__module__].get_conv_template
        template = get_template(self.model.template)
        template.system_message = payload['system_prompt']
        question = ''.join(f'Panel {i+1}: <image>\n' for i in range(len(images))) + payload['user_prompt']
        template.append_message(template.roles[0], question)
        template.append_message(template.roles[1], None)
        query = template.get_prompt()
        self.model.img_context_token_id = self.tokenizer.convert_tokens_to_ids('<IMG_CONTEXT>')
        for n in counts:
            query = query.replace('<image>', '<img>' + '<IMG_CONTEXT>' * self.model.num_image_token * n + '</img>', 1)
        inputs = self.tokenizer(query, return_tensors='pt').to('cuda:0')
        output = self.model.generate(pixel_values=pixels, input_ids=inputs.input_ids,
            attention_mask=inputs.attention_mask, max_new_tokens=1024, do_sample=False,
            eos_token_id=self.tokenizer.convert_tokens_to_ids(template.sep.strip()))
        text = self.tokenizer.batch_decode(output, skip_special_tokens=True)[0].split(template.sep.strip())[0].strip()
        return text, int(inputs.input_ids.shape[-1]), int(output.shape[-1]), dict(
            image_count=len(images), num_patches_list=counts, pixel_values_shape=list(pixels.shape),
            image_context_tokens=self.model.num_image_token * sum(counts))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', choices=CONFIGS, required=True)
    parser.add_argument('--allowed-root', type=Path, required=True)
    parser.add_argument('--port', type=int, default=PORT)
    args = parser.parse_args()
    # Reserve the port before allocating weights, avoiding accidental use of another service.
    server = HTTPServer(('127.0.0.1', args.port), BaseHTTPRequestHandler)
    engine = Engine(args.model, args.allowed_root)
    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, body):
            value = json.dumps(body).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(value)))
            self.end_headers()
            self.wfile.write(value)
        def do_GET(self):
            self.reply(200 if self.path == '/health' else 404, engine.info if self.path == '/health' else {})
        def do_POST(self):
            if self.path != '/complete':
                return self.reply(404, {})
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size < 2_000_000:
                    raise ValueError('Request size invalid')
                result = engine.complete(json.loads(self.rfile.read(size)))
            except Exception as exc:
                traceback.print_exc()
                return self.reply(500, dict(error_type=type(exc).__name__, error=str(exc)))
            self.reply(200, result)
        def log_message(self, fmt, *args):
            print('HTTP ' + fmt % args, flush=True)
    server.RequestHandlerClass = Handler
    server.serve_forever()


if __name__ == '__main__':
    main()
