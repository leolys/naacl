# ob_paper_revision_20260930

Reviewer-requested revision experiments for the NAACL-2027 submission.

Arms
- `plain/seed{12345,22345,32345}`: direct selection, 1 request/task/seed.
- `v5/seed{...}`: full verification configuration, 3 requests/task/seed.
- `sc3`: majority vote over the three plain seeds (no new requests).
- `tab/tab`: two-phase tabular answering (transcribe, then decide from table without image), 2 requests/task.
- `clean/clean`: direct selection on the paired clean chart (`clean_benchmark_v1/assets/<task>/clean.png`), 1 request/task, scored against the original label.

Engine: Qwen3.8-27B BF16 local vLLM (port 8058), decoding identical to the
frozen ob_full_comparison config (temperature 0.7, top_p 0.8, top_k 20,
thinking off, max_pixels 1605632); `max_num_seqs=4` on the single-GPU lab.
All comparisons are within this configuration.

Scoring: `python3 scores.py --out results` -> `results/scores.json`
(full-denominator original-label agreement; exact McNemar within seed;
conservative paired-difference CI; seed mean/stdev).
