# Revision experiment status (2026-09-30)

## Completed arms
- plain x3 seeds (420/420 ok): targets 79/77/80 (mean 78.67, sd 1.53)
- clean control (140/140 ok): 115 target (82.1%); paired vs plain seed12345: +33, p=3.6e-8, CI [+0.162,+0.270]
- tab bounded (122/140 ok, 18 transcribe 'length' failures kept as IF): 40 target / 23 trap / 4 other / 55 no_option abstentions; paired net -3, p=0.51; sc3: 75 (75/140), net -3, p=0.375

## Running
- v5 x3 seeds on lab job_1790762921784_cxsngd (idempotent runner, results/runs/v5/seed*/)
- Server: full frozen flags + --no-async-scheduling, max_num_seqs=8 (only deviation), port 8058

## After v5 completes
1. vllm-venv/bin/python scores.py --out results   (re-run; includes v5 per-seed + pooled)
2. Copy numbers into paper/naacl2027/sections/04_experiments.tex:
   - tab:static-seed V5 row (mean±sd, mean net, pooled McNemar)
   - baselines paragraph final sentence (seed variance sentence)
   - fold the single-run replication paragraph into seed discussion
   - abstract static-panel sentence (within-run replicated framing)
3. Final B1 compression to ~8.5 body pages; pdflatex+bibtex; commit+push

## Gotchas learned
- lab_exec pkill -f self-match: never put a pattern-matching token in the same command line; kill by PID list.
- Runner idempotency skips FAILED files too: purge non-ok files before gap-fill reruns.
- Server wedges under sustained load with default async scheduling; --no-async-scheduling + full frozen flags fixed it.

## 2026-09-30 晚间更新
- 页限确认:NAACL 2027(ARR 2026-10 轮)长文正文 8 页,Limitations/Ethics/References/附录不计。正文已压至恰好 8.0 页(结论末句在 p8 底部)。
- Lab 机器被重置(全新实例,无 /data、无 GPU)。三种子复现原始 run JSON 未回传,已随机器丢失;所有统计数字已在正文+本文件中锁定。如投稿需 artifact,需在新机器重建 vLLM 环境重跑(约 4-6h GPU)。
- 残留 TODO:P16 提交前 XXX 全文扫描(正文 sections 目前干净,仅 main.tex 有 ARR Paper ID 占位)。
