#!/bin/bash
# Full xmodel pipeline: serve M2 -> run -> serve M1 -> run -> eval + auto-upload.
# Experiment end automatically triggers evidence upload to GitHub (auto_upload.sh).
set -uo pipefail
XM=$(cd "$(dirname "$0")" && pwd)
PANEL=$XM/..
PY=$(command -v python3)
MODELS=/data/lab/models
LOGDIR=$XM/pipeline_logs
mkdir -p "$LOGDIR"
wait_health() { for i in $(seq 1 120); do sleep 5; curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$1/health" | grep -q 200 && return 0; done; return 1; }

run_model() { # dir name port thinking_flag
  local dir=$1 name=$2 port=$3 thinking=$4 extra=${5:-}
  echo "== serving $name on :$port $(date -u +%FT%TZ) =="
  bash "$XM/serve_xmodel.sh" "$MODELS/$dir" "$name" "$port" "$extra" \
      > "$LOGDIR/serve_${name}.log" 2>&1 &
  SERVER_PID=$!
  wait_health "$port" || { echo "serve failed for $name"; tail -30 "$LOGDIR/serve_${name}.log"; kill $SERVER_PID 2>/dev/null; return 1; }
  echo "== server up; starting runner $name =="
  local think_args=""
  [ "$thinking" = "yes" ] && think_args="--enable-thinking"
  $PY "$XM/run_xmodel.py" --model "$name" --endpoint "http://127.0.0.1:$port/v1" \
      --versions plain,v3,v4,v5,v6,v7 --concurrency 16 $think_args \
      --out "$XM/runs_xmodel/$name" > "$LOGDIR/run_${name}.log" 2>&1
  local rc=$?
  echo "== runner $name rc=$rc $(date -u +%FT%TZ) =="
  kill $SERVER_PID 2>/dev/null; wait $SERVER_PID 2>/dev/null
  sleep 10   # free GPU memory before next model
  return $rc
}

FAIL=0
run_model Qwen3-VL-8B-Instruct Qwen3-VL-8B-Instruct 8057 no || FAIL=1
run_model Qwen3.8-27B Qwen3.8-27B 8058 yes "--reasoning-parser qwen3" || FAIL=1
if [ $FAIL = 0 ]; then
  echo "== pipeline complete; auto upload =="
  bash "$XM/auto_upload.sh" "$XM" xmodel-20260928-v1 || FAIL=1
else
  echo "== pipeline had failures; auto upload skipped =="
fi
echo "== pipeline exit status: FAIL=$FAIL =="
exit $FAIL
