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

## 2026-09-30 第二轮评审修复(评审→修复→复审闭环)
- 第二轮评审复核中本地取证的意外收获:xmodel/runs_xmodel 含 27B 复刻轮与 8B 轮逐任务结果,Table 1 全部 12 个 Δ/p 格逐格复核完全吻合;原始轮 token 总额 8,856,548 ≈ 8.86M 吻合。
- 4 个新阻塞项全部修复(均为本轮编辑引入/暴露的笔误):
  1. tab:online-four Batch A Ordinary×mis Fail 5→2(行合计恢复 12);
  2. 摘要 8B 迁移 46.4%→57.1% 为 V7 之数,改回 V5 的 53.6%;
  3. §4.2 迁移拆分 11/5 → 14/2(本地逐任务真值);
  4. 附录开发集句改为:复刻轮 +17=+16(116)+1(dev),原始轮 +13/+2,8B 轮 +9/+1;"headline gain"句改为"at most two decision points"。
- Should-fix 5 项 + Polish 4 项完成:Fig.1 重制(2 行短标题,无碰撞);Limitations 保存声明按轮次限定(三种子复现仅存汇总统计,诚实披露);3–5→0–5;luo2026agentic 移出记忆综述句(§4.3 中的弃权引用保留);摘要"in a frozen rerun"+正文"single-run rerun";摘要"against the baselines";intro 26 点锚改为"across runs on the paired faithful charts";Eq.2 第三槽位与散文一致化;删除死标签 sec:method:example。
- 未做(有意):两条可选引文(rabanser2026towards, zhang2026prompt)——正文刀刃 8.0 页,无页数预算;已记录。
- 修复后:正文仍恰 8.0 页(Limitations 标题 p9 顶部),15 页,0 undefined。

## 2026-09-30 第三轮评审修复(评审→修复闭环)
- 第三轮 PAPERGURU 评审(Overall 3.5 Borderline Conference;修复后可 4.0)逐条修复,全部先对本地原始数据取证:
  B1 接口失败账目改为逐轮真值:Direct 1/0/1、V3 6/8/51、V4 0/2/2、V5 0/3/4、V6 2/2/8、V7 0/1/2(original/rerun/8B),none discarded;
  B2 稳定性重跑三处改写:摘要/§4.3/附录统一为"37/48 保持提交边界同侧(四分类 31/48),其余在弃答、工程失败、调用上限终止间移动,两轮均零错误提交";边界声明 2 四分类格位移 ≤2→≤3(Defense×misleading Fail 2→5);
  B3 §4.1 复算声明限定"outside the three-seed replication"(与保存声明一致);
  新发现:静态面板空选择(completed 无标签)全配置存在(plain 0、v3 13/21/4、v4 9/11/6、v5 6/5/8、v6 13/12/5、v7 5/5/3),据此修正 §4.2 两处弃答表述:"no increase in abstention"→"0 interface failures against Direct's 1 + 空选择留在分母";"abstention-free outside V3"→"interface failures concentrate in V3, no configuration abstains explicitly";
  S1 池来源披露:O/B 记录"pre-generated from the chart and public task"(§3.3+§4.1)+附录成本段新增 136 任务早期前沿模型批次/4 任务 Qwen、一次性生成成本不计入 per-task 请求账目;
  S2 术语统一:Table 1 列头+附录 B4+成本段 "27B replication"→"27B rerun"(保留 matched-configuration replication 仅指 Table 2);
  S3 Fig.1 caption 补 "$B_0$";S4 pilot 句移至配对效应句后;S5 Limitations 新增 Baseline coverage 段(指令硬化基线未跑);S6 Table 2 列头 "Req. (runs summed)";S7 Table 1 caption 补 "stratification";
  Polish:Fig.1 y 轴 "Printed value";贡献拆两句;§4.2 "one-directional: 57 keep, 33 e→t, 14 t→e, 2 t→empty"。
- 页限:全部编辑(净 +0)后正文仍恰 8.0 页(Conclusion 标题 p8 y502,Limitations 标题 p9 y72),15 页,0 undefined。
- PDF 验证:14 处编辑全部在成品 PDF 中 grep 落位(含 1/0/1、31/48、at most three units、136 tasks by an earlier frontier、Printed value 等)。
- 有意跳过:3 条可选引文(HarnessRisk 2608.17597、From Prompts to Contracts 2607.08028、rabanser2026towards)——8.0 页刀刃无预算;轮 3 评审的"机械数字审计脚本"建议已采纳(本轮全部数字逐格复算即为落实)。
