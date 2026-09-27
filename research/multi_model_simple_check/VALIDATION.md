# Document-following validation (no task inference)

Run the following three commands verbatim from PowerShell on the desktop. Do not improvise if any fails. Report exit codes and witness output. Latest explicit user permission permits sharing GPU 7; `--allow-shared-gpu` records this choice, checks free memory, and never stops others. No models are loaded, no API request, no shared environment modification. A passing witness proves kernels and the documented command, NOT model inference or research quality. Full native model inference is separately checked by recorded non-chart controls.

```powershell
ssh hexin_2007_K_root 'cd /mnt/data/lys/CognitiveHijacking_CognitiveDenial && env CUDA_VISIBLE_DEVICES=7 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 WANDB_DISABLED=true /mnt/data/code_generation/liyisheng/8H100conda/envs/qwen3_vl/bin/python -m research.multi_model_simple_check.environment --witness --allow-shared-gpu'
```

Expected: exit 0; WITNESS, spec_hash 563c93e4, visible_device 7, shape [32,32], NVIDIA H100 80GB HBM3; sum approximately 1019.2579956054688. Versions torch 2.8.0 / transformers 4.57.1.

```powershell
ssh hexin_2007_K_root 'cd /mnt/data/lys/CognitiveHijacking_CognitiveDenial && env CUDA_VISIBLE_DEVICES=7 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 WANDB_DISABLED=true /mnt/data/code_generation/liyisheng/8H100conda/envs/internvl/bin/python -m research.multi_model_simple_check.environment --witness --allow-shared-gpu'
```

Same expected witness for the second existing environment.

```powershell
ssh hexin_2007_K_root 'cd /mnt/data/lys/CognitiveHijacking_CognitiveDenial && env OMP_NUM_THREADS=4 LD_LIBRARY_PATH=/mnt/data/lys/CognitiveHijacking_CognitiveDenial/research/multi_model_simple_check/runtime/browser_libs/usr/lib/x86_64-linux-gnu /mnt/data/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -m research.multi_model_simple_check.environment --browser-witness'
```

Expected: exit 0; BROWSER_WITNESS 125.0.6422.26.

## Full wave invocation (executor only; reviewer must not run)

After the probes and focused tests pass, from remote project root:

```bash
/mnt/data/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -m research.multi_model_simple_check.run --prepare
screen -L -Logfile research/multi_model_simple_check/runs/extension_20260916_v1/wave.log -dmS misvis_multi_20260916 /mnt/data/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -u -m research.multi_model_simple_check.launch --execute --allow-shared-gpu
```

The launcher binds GPU 7, serially loads only the three predeclared local models, records its PIDs and cleans up only its own child services. No implicit model or resource fallback. `wave_status.json` and each `final_status.json` are the authoritative completion/failure state, not screen presence. If a service fails, preserve its log; no blind relaunch.
