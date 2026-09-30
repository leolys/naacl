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

## 2026-09-30 第四轮评审修复(Phase 5 清单逐条执行)
- Blocker 3 项:1) Table 2 caption 插入"the tabular arm on its 67 selected units"(表列法配对限制说明,配对句压缩补偿);2) 附录分层句"27B replication"→"original round"(轮次归属纠错,本地数据核实 -5 属原始轮)并消除"both model rounds"歧义;3) §4.3 新增净图成本句(Batch C/rerun:6 和 5 对 10)+附录 Online Deployment Details 全四批量化(3/2/6/5 对 10/12/10/10)。
- Should-fix 7 项:4) §4.2 迁移段后新增多重性句("These exact tests are unadjusted for multiplicity; on the 8B columns we read V4--V7's consistent directionality, not single-test significance.");5) "Interface-Failure Accounting"→"Non-Scoring Outcomes",新增空选择逐轮账目(Direct 0/0/3、V3 13/21/4、V4 9/11/6、V5 6/5/8、V6 13/12/5、V7 5/5/3;原始轮经 analysis/final_001/*.json counts.no_option 独立再取证,rerun/8B 轮经 runs_xmodel 逐任务复算);6) 新增两条 session 内 paper_search 逐字引文:leong2026injectionexecution(2605.08442,Limitions state-integrity 段)、lan2026seeing(2605.22903,measurement 段基准效度警告);7) intro 26 点锚改为"(rate gap on seed means; paired net +33)"区分两种量;8) Limitations 新增 interface-content×prompt-content 混杂声明(8B 归因为失效模式分解论证,未做交叉消融);9) Table 1 caption "abstentions"→"empty selections";10) 附录请求账目补名义全跑 2,240 与早终止差额说明。
- Polish:11a 摘要句拆分;11b 方法 L130 句拆;11c 园径句改写;11d "no configuration can abstain: every unit must select";11e 成本段句拆;p=0.044→p=.044 统一;item 12(p_i 取值范围)有意跳过——正文刀刃 8.0 页,L101-103 已隐含该信息,记录在案。
- 页限:全部新增(多重性句、净图成本句、caption 扩句)由 §4 内 27 处等量压缩吸收,正文仍恰 8.0 页(Conclusion p8 y505、Limitations p9 y72),15 页,0 undefined;42 条 bib,bibtex 重跑通过。
- ref_verify(42 条):10 corrected/32 UNVERIFIED;UNVERIFIED 均为 arXiv 前印本与经典条目(CrossRef/OpenAlex 无记录),全部源自本 session paper_search 逐字输出或此前已验证集合,按轮 2 既定惯例保留;corrected 负载未随报告返回,故 .bib 保持已定稿状态并在此记录。

## 2026-09-30 第五轮评审修复(Phase 5 清单逐条执行)
- 首要:纠正轮 4 的执行缺口——轮 4 报告称已修附录轮次归属,但编辑脚本从未包含该修改;本轮 B1 落实:附录 L304 "27B replication"→"original round"、"both model rounds"→"both rounds compared here"。
- B2:§4.2 恢复 "of Table~\ref{tab:static-main}" 锚(轮 4 补偿造成的悬空指代),同句内压缩补偿("comparisons must stay within-run")。
- B3:附录池来源句补充"are not a strictly blind construction (a minority of records carry task-directional hints that verification must re-justify against the chart)"——与 PROTOCOL.md "部分B含行动含义,不是严格C盲审" 对齐,消除报告-补充材料一致性隐患。
- S1:§4.1 新增 V 阶梯动机句("The five variants trade verification content against interface strictness: what is checked versus how answers are forced."),补偿:policy-boundary→policy、schema-typed→typed、item by item→itemwise、must submit a selection→must select、recorded reason→reason、a real→a、direct selection and V5→Direct and V5。
- S2:§4.2 配对说法统一为 "paired clean charts";S3:"a frontier model, gpt-5.6-terra,"(定冠词先行词已随 pilot 句移位而消失);S4:双冒号长句拆分;S5:"drawing on the frozen per-task pool";S6:"The panel's exact tests are unadjusted for multiplicity"。
- 有意跳过:P1 ahn2026lies(2608.30428,为欺骗生成方向,切题度低,8.0 页刀刃无预算);P10 ARR 投稿表 Datasets/Software 字段——属提交时操作,已列投稿日 TODO。
- 页限:正文仍恰 8.0 页(Conclusion p8 y505、Limitations p9 y72),15 页,0 undefined。
- 验证纪律(本轮评审提出):每项修复以 PDF 文本逐项落位确认(L749/L759/L794/L1240/L1466),不再以计划为准。

## 2026-09-30 第六轮评审修复(Phase 5 清单逐条执行)
- B1(阻塞,本轮核心):轮 6 全量 48 单元普查(修正版分类器)发现配对效应措辞把 11/23 个转换误称为"记录在案的弃答"。真实拆分:Batch C 转换 10 = 7 弃答(5 误导+2 净图)+3 工程失败;重跑轮转换 13 = 5 弃答(3+2)+8 终止(7 工程失败+1 调用上限)。摘要还误加了"误导图"限定(10/13 跨两种图)。三处落位:04_experiments L183-196(拆分+合并符号检验:12 个已解析转换 12vs0,p=2×2⁻¹²≈4.9×10⁻⁴<.001)、00_abstract(12/23 弃答转换+11 终止,去图表限定)、07_appendix 边界三(附录不限页,写全拆分)。过程教训:前五轮验证只核对了计数(10/13、反向 0)与精度,未把单元状态分布对齐到"弃答"一词——轮 6 起每个状态性措辞都要对原始 status 分布审计。
- S1:§4.2 重跑句补机制从句"in a fresh serving process of the identical configuration (serving-side batch admission is a nondeterminism source at a fixed seed)",吸收掉含糊的"quantifying sampling variance"。依据:xmodel_20260928 为独立服务进程(端口 8057),与 9/27 四服务部署分离。
- S2:精度分母澄清为 batch-wide(26=18+8,27=20+7)并补防御臂 8/8、7/7(普查证实)。
- S3:Batch C 接口句量化"abstention dominant among non-submissions (11 of 16)"(11 弃答+1 bug+4 失败=16 非提交)。
- P5:§2 方法侧列表插入 TrustBench(sharma2026realtime,ACM CAIS'26,DOI 10.1145/3786335.3813145,arXiv 2605.05287)。refs.bib 两处必要修正(偏离逐字复制,按轮 2 修正先例):作者列表逗号→and 连接(逗号版被 BibTeX 解析为单人名,bbl 渲染"Pragya~Sharma Tavishi~Sharma, Vinayak~Sharma"乱序);title 加 {TrustBench} 大小写保护(bst 会把系统名小写)。
- P6:改写消除"strictly one-directional/rather than corrections"三重复;P7:镜像成本句 em-dash 同位语→括号。
- 补偿(§4 内等量吸收):V 阶梯阐述半句、stability 句枚举(分类学已在 B1 句中)、per-seed 指向、tabular 基线短语、(Playwright-controlled)、or variant、four-batch、Structural and semantic、executing agent's、cannot be taken for granted→is not guaranteed。摘要内:open-weight、holds 去重、12/23、or chart variant。
- 页限:Conclusion p8 y511、Limitations p9 y72(与轮 5 完全一致),15 页,0 undefined。
- 验证:pdftotext+归一化逐项落位(17 项 OK + 7 项旧文本 GONE);pdfplumber 抽取有空格合并怪癖,本轮起以 pdftotext 为成品验证基准。

## 2026-09-30 第七轮评审修复(Phase 5 清单逐条执行)
- B1(阻塞):结论收束句"residual errors becoming legible abstentions"是轮 6 分类学纠正未传导到的第三处(结论段),与 §4.3 新拆分自相矛盾。改为"residual mass becomes recorded abstentions or unrecovered terminations",同段删"recorded"(Keep/Revise/Unresolved 本身即记录)补偿。
- S1:Limitations 请求计数补账本归属"(2,230 requests for 840 decisions in the 27B rerun ledger)"——原轮账本记 2,240 次"尝试"(含重试),重跑账本 REPORT_XMODEL_20260928.md L139 记 2,230,两数并存须指明口径;附录 app:details 本就披露 2,230/2,184 对名义 2,240。
- S2(就地解决,无编辑):PREPARATION.json 明确登记 n_records=275(哈希锚定封存准备账本,源清单 ob_refinement_20260927/manifest.json)——"275 across the panel"(§3 与 §4.1)有据。原轮 8.86M 亦为账本 known_usage 合计 8,856,548 ✓;重跑 8.84M/8B 8.14M 与 REPORT_XMODEL M1/M2 行吻合 ✓。
- S3:app:details 补"token totals are known-usage sums from each round's request ledger"(原轮账本按 known_usage 记账,无用量请求不计,8.86M 为下界)。
- P5 有意跳过:zhang2026images(EACL 2026,10.18653/v1/2026.eacl-long.323)入 §2 需约 +70 字符且无干净补偿(刀刃页限),与轮 5 跳过 ahn2026lies 同理由;已记录待 camera-ready 或页限放宽时补。
- P6:"So K"→"Thus K";P7 记投稿日 TODO:ARR 表 Datasets/Software 字段 + "NAACL-2027-XXXX" 占位符替换为 ARR 分配号。
- 页限教训:§4 内删减被 [t] 浮动体钉住的版面吸收,不传导到结论段;结论段 17 字符净增把孤词"chart."挤出第 8 页→Limitations 标题 p9 y72→y97。补偿必须在结论段内部做:删"afterwards"(含义由 keep revised rules in force 承担)后孤词回位,边界恢复 p9 y72。另做 §4.1 池描述去重(§3/§4.1 逐字重复,"frozen per-task pool of one to three O/B records"现全文仅 1 处于 §3,§4.1 改为交叉引用)与"fixed identifier order"入补充材料两项页限补偿。
- 页限:Conclusion p8 y511、Limitations p9 y72(轮 6 状态),15 页,0 undefined。
- 验证:pdftotext+归一化 8 项新文本 OK、4 项旧措辞 GONE、池描述计数=1。

## 2026-09-30 第八轮评审修复 + 图表扩充(附录不计页)
- B1(阻塞,唯一数字错误):app:interface"12 unresolved_public_evidence verdicts"与自身 Table 3 及轮 6 普查矛盾(应为 11+1 预算耗尽;疑为与摘要"12/23 转换"串号)。改为"11 … verdicts (7 on misleading charts) and one re-verification-budget exhaustion"。预算耗尽单元在 \ours{}×misleading 行(Table 3 Bug.=1)。
- 重大归属审计(轮 8 评审 S1 猜测被原始数据复算纠正):app:details 分层增益散文对 (16,4)(0,9)(6,6)(5,9) 与 (18,11)(3,2) 全部与 (27B rerun, 8B) 对精确吻合(rerun 域和=+17、8B=+10,复算 scorer 与表 1 全格一致),并非 (original, 8B)。据此:L301"−5 in the original round"→"−5 in the 27B rerun"(original 实为 −3);L303"+18 (original round)"→"+18 (27B rerun)";"dual-axis and non-linear-axis … second model round (−5 and −6)"实为混轮(双轴 −5 属 rerun、非线性 −6 属 8B),改写为各自归属;"in both rounds(−5,−9)"→"in every round(−3,−5,−9)"(original 环境域 −3 也是唯一负域,原句漏掉)。app:transfer"against 8 and 6 in the other rounds"→"against 8 in the 27B rerun and 6 in the original round"。
- 附录新增(数据全部由原始记录复算,scorer 以 gold labels 对 840+840 单元重打分,orig 全格 81/74/87/96/84/91、rerun 73/90、8B 65/75 精确复现):
  - 表 3 机制族分层(21 族×n×三轮 V5−Direct 净增益,行和=+15/+17/+10 与头条闭合;族名英文缩写,caption 声明 manifest 固定分组、含变式、非 21 独立机制);
  - 表 4 域分层(business+11/16/4、env−3/−5/−9、health+5/6/6、public+2/0/9);
  - B.2 成本台账小节+表 5(原轮 per-config attempts/tokens 全格+两模型轮 tokens;总行 2,236/8,856,548、2,230/8,840,896、2,184/8,136,969;正文披露 xmodel 轮各 9/6 条无 usage 事件;两模型轮 per-config 尝试数因列宽改为只在正文引用——8B v3 375 次(51 接口失败所致)等已在账本);
  - B.7 转换结果小节+图 2(fig_conversions.pdf,make_fig_conversions.py,堆叠条形:Batch C 10=弃答7+工程3、重跑 13=弃答5+工程7+调用上限1;标注"23 conversions: 0 corrections, 0 wrong submissions";弃答拆分 8 误导/4 净图、工程 6/4、调用上限在净图,均由 002/003 summary.json scores[] 逐单元复算);
  - 表 7 非记分台账(IF/ES×6配置×3轮 36 格与散文及 SUMMARY/账本全一致)。
- 版面危机与修复:三张新表初版超宽(family 155pt、cost 150pt、nonscoring 67pt Overfull)互相压印(p13 目检确认)。修复:family \small+tabcolsep 4pt+族名缩写;cost 改 5 列(\small+tabcolsep 3pt,去掉两模型轮 attempts 列);nonscoring \small+tabcolsep 3pt。全部清零。既有缺陷顺手修:eq:pub013(式 8)原文超宽 39.7pt 横向压印右栏正文,用 aligned 拆两行(编号不变,无 \ref 依赖)。
- Overfull 教训:table 环境的"Overfull in paragraph"警告对既有 Table 1(225pt)/Table 2(143pt)是伪影(八轮评审像素级正常),不能只看警告数字——本轮真缺陷靠渲染页 PNG 目检判定;警告归因用日志文件栈(regexp 最近一次 (./sections/)。
- Algorithm 1 浮动到末页(p16)为既有行为(旧版 p15 同样),非回归,未动。
- 页限:Conclusion p8 y512(±1pt 舍入,正文未动)、Limitations p9 y72 精确,16 页(附录+1),0 undefined,overfull 6→4(余 4 条均为未触区域既有项,像素无碍)。
- 验证:pdftotext+归一化全项 OK(B1 新句在、旧句 GONE、七表/图 caption 落位、表号链 T3–T7 与正文 \ref 自动一致、正文"Table 6 gives the full decomposition"自动更新);p12/13/14/15/16 渲染目检通过;Figure 2 嵌入页 15(log 确认 <./fig_conversions.pdf>)。
- 有意跳过:机制族表不加正文引用(§4.1"21 mechanism families"在刀刃上,附录表由小节自引);zhang2026images 仍记 camera-ready 待办;ARR 表单字段仍记投稿日 TODO。

## 2026-09-30 第九轮:轮 9 终审评审(交付,修复未执行)+ 用户图表指令执行
- 轮 9 评审已交付:零阻塞(首次),Overall 4/Conference、Soundness 5、Confidence 5;should-fix ①itkin2026delayed(arXiv 2606.27409,≤6mo,插 §2 L3 后 ~45 字符,补偿候选=§2"what was verified, not a verdict about the answer"半句,该补偿句本轮确认仍未动);②B.1/B.9 域句去重(附录不计页);③投稿日任务:所有作者 ARR reviewer 注册硬截止 10-12、NAACL/COLING 共享 ARR 周期 commitment(12-23)定 primary、ARR 表单字段、Paper ID 替换。修复等用户指示。
- 用户指令:①图丰富自然 ②缺主图,如何画 ③附录表移正文。执行①②,③给账本结论(见下)。
- 图 1 丰富(make_fig.py 重写):6 点→12 点带真实感波动序列(同数据双面板不变,"same drawn series"消息不变),轴题 Week/Units sold (k),刻度标签每 2 周,y 网格线,marker/线宽调细;figsize 不变,边界 p9 y72 复核后确认无漂移。
- 图 2 重设计为流图(make_fig_conversions.py 重写,Sankey-lite:左源节点 Batch C 18/重跑 20 ordinary-correct,右结果节点 Correct submission 15/Abstention 12/Engineering 10/Call limit 1,缎带宽度∝计数+每条流量数 8/7/3/7/5/7/1;底注"Defense-arm wrong submissions: 0 of 96 units")。38=15+23 分解由原始记录复算验证(C: 18=8+7+3,重跑: 20=7+5+7+1;defense 正确提交总数 26/26 与 27/27 不变,15 只是 ordinary-correct 子集)。caption 更新为 38 单元口径。
- 主图(用户问"如何画",已实现):fig_overview.pdf + make_fig_overview.py,方法总览 5 框闭环(Agent judgment O∧B⇒C_q(a) → Competing chains K(frozen pool, same chart) → Applicability verifier L(observation/rule/derivation vs in-chart evidence) → Terminal status(Keep/Revise/Unresolved) → Persistent rule state M(revision+evidence+scope, written only by verification),回环"later steps read scope-matched rules→re-derive";对角标注 validated revisions)。全部措辞取自 §3 原概念,无新主张。置于 §3 开头 [t],指针句加在 §3 进程句"(Figure 2)";自动编号:误导对=图 1、总览=图 2、转换=图 3(全 \ref 自动)。
- **重大发现(轮 8"伪影"结论是误诊)**:正文 Table 1/2 自创建起真实超宽(自然宽 ~437/354pt vs 栏宽 ~220pt),八轮"像素验证"漏检因 pdftoppm 在页缘裁剪+浮动位置变化使出血时而是离页裁剪(不可见)时而压邻栏。旧版 b41e1ff9 p7 上 T1/T2 互相压印、T1 的 p/95%CI 两列被页缘物理裁掉。修复:T1→\small+tabcolsep 3pt+去两处 1.5em 额外间距+9 列(去两个 CI 列),10 个 CI 全文迁入 app:transfer 首句(附录不计页,逐字来自原表),caption 补"Column groups in order"+CI 指针;T2→\footnotesize+tabcolsep 2pt+表头 Req.(sum)/Acc.("0 extra"→"0",caption 已有 runs summed 语义)。修复后 T1 x71-291、T2 x306-526 全部落栏。
- 连带发现与修复:Table 6(online-four)真实超宽 67.5pt(p14 右缘出血至 x586,轮 8 的 67pt 修复记在 T7 头上而 T6 漏修)→\footnotesize+tabcolsep 3pt,x306-524 落栏。全文出血扫描(x1>560 与左栏 298<x1<314)清零;eq:read 23.1pt 警告经 p5 目检为内部 hbox 警告、渲染 contained,保留不动(真伪影);T2 余 0.59pt 不可见。
- 主图进正文的腾挪(内容保全):§4.1 V3-V7 变体梯句→新附录小节 app:ladder(Configuration Ladder,B.1);§4.3 六任务试点句→B.8 转换小节;§4.2/4.1 去重与压缩六处(57.9/68.6 率删[摘要已有]、SC3/tabular 机制括号[附录 B.9 已有]、serving-side、per-seed 指向、post-selection 短语、接口分解压缩、baselines 句压缩、275 records 缩短);净腾挪≈新增图块代价,正文回到 8.0 页整。
- 表 2 caption 未动(Req./Acc. 由 caption 措辞覆盖);表号链 T1-T7、图 1-3、算法 1 全部 \ref 自动一致。
- 页限:16 页,Limitations p9 L y72 精确(正文 8.0 页整),0 undefined,overfull 2(均无视觉缺陷)。
- ③附录表移正文的结论(已告知用户):正文 8.0 页零富余,晋升任何附录表需删 ~0.5 栏真实散文;推荐 camera-ready(+1 页)时晋升表 4(域分层)与表 7(非记分),或用户明示 trade 再动。
- 验证:pdftotext 直查三片段(CI 指针/Req.(sum)/CI 句)全 OK;图编号 Figure 1/2/3 全渲染;p7/p8/p13/p14/p16 目检通过;x1>560 与左栏出血双扫描清零;正文文本 battery 全 OK(pilot 恰 1 次、ladder 指针/附录小节、post-selection、SC3 compressed、records trim)。
- 有意跳过:itkin2026delayed 引文与 B.1/B.9 去重(轮 9 should-fix,等用户指示);zhang2026images/ARR 表单仍记待办。
