#!/bin/bash
# xmodel serving script. Params mirror the archived service_config.json (BF16,
# TP=1, 16k ctx, num_seqs 1, eager, mm image cap 1605632) on a fresh endpoint.
set -euo pipefail
MODEL_PATH=$1   # e.g. /data/lab/models/Qwen3-VL-8B-Instruct
NAME=$2         # served name, must equal runner --model
PORT=$3
EXTRA=${4:-}

export PATH="$HOME/.local/bin:$PATH"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1
export VLLM_NO_USAGE_STATS=1 OMP_NUM_THREADS=8 TOKENIZERS_PARALLELISM=false PYTHONUNBUFFERED=1

VLLM_BIN=${VLLM_BIN:-$HOME/.local/bin/vllm}
if [ ! -x "$VLLM_BIN" ]; then VLLM_BIN="python3 -m vllm"; fi

exec $VLLM_BIN serve "$MODEL_PATH" \
  --served-model-name "$NAME" \
  --host 127.0.0.1 --port "$PORT" \
  --dtype bfloat16 \
  --tensor-parallel-size 1 \
  --max-model-len 16384 \
  --max-num-seqs 16 \
  --max-num-batched-tokens 4096 \
  --gpu-memory-utilization 0.88 \
  --limit-mm-per-prompt '{"image": 1, "video": 0}' \
  --mm-processor-kwargs '{"max_pixels": 1605632}' \
  --enforce-eager \
  $EXTRA
