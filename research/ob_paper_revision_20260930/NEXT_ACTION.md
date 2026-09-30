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

## 2026-09-30 深夜更新:第二轮评审修复完成
- 全新 PAPERGURU 评审(Overall 3.5/Accept, 3 Blocker + 7 Should-fix + Polish)已逐条修复:
  B1 请求计数 12/task→9/task(V5=3请求×3种子);B2 模型全名 Qwen3.8-27B/Qwen3-VL-8B-Instruct/Playwright 落位;
  B3 前沿模型 gpt-5.6-terra 落位(§4.1+附录表 Batch C 标头);S1 tab:online-four 扩为 4 块(A/B/C/重跑)+Wrong 列;
  S2/S7 新增 6 条 2026 引文(harness 综述/agent 弃权/记忆综述/状态完整性/同组 VLM bias);
  S3 状态写入威胁模型句(§3.4+Limitations state-integrity 段引 louck2026securing);S4 caption 配对语义分离;
  S5 L=1;S6 冻结声明;Batch A "22 of 24"→"20 of 24(17 处 SchemaError)"+六次错误提交全部在 A/B 批 ordinary 臂;
  附录 A.2-A.4 合并为 Mechanistic Details;2.6× 精确化(2,230 请求/840 决策);Keep/Revise/Unresolved 大小写;p/CI 格式统一为 APA 式(去前导零)。
- 页限:评审新增内容一度把正文推到 8.43 页;三轮等量压缩后正文仍恰 8.0 页(Limitations 标题 p9 顶部,结论在 p8 底部结束),共 15 页 PDF。
- ref_verify:40 条中 1 verified/17 corrected/22 UNVERIFIED。UNVERIFIED 均为超新 arXiv 条目(数据库覆盖不足)或经典条目(字段格式查证失败),
  每条均可溯源:或来自此前已验证集合,或来自本 session paper_search 逐字输出。保留并在本文件记录理由。
- 遗留(需 artifact 重跑才能补):SC3 配对平票数(p=.375)未报告;SC3 tie 数据随 lab 重置丢失,不臆造。
- P16 已完成:sections 全文无 XXX/TODO,仅 main.tex 保留 ARR 模板必需的 Paper ID 占位。
