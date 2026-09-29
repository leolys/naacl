# GUI-Reflection baseline 运行状态（2026-08-30）

## 结论

官方 GUI-Reflection 代码和 `GUI_Reflection_8b_SFT` 四个权重分片已经完整落盘、逐分片校验，并在单张 H100 上用官方 `GUI_Reflection_Agent` 成功加载和真实推理。不存在普通 InternVL、API 模型或 mock policy 回退。

本次实际获得了两组结果：

- travel Natural misleading/clean：2 条模型轨迹、每条 6 步；模型未进入 chart/trap 分支，所有点击都没有改变 URL，最后无提交即输出 `TASK_COMPLETE`。两臂原始输出逐字相同，因此该组结果被前置 Web grounding 失败截断，不能估计视觉纠错效果。
- formal `smoke17`：17 个配对任务、34/34 个请求单元均保留；official 和 clean 均为 `0/17` hidden-scored success，34 个单元均无隐藏提交。27 条由模型提前输出 `TASK_COMPLETE`，6 条跑满 20 步超时，1 条因模型点击根任务列表而被 containment 拦截。

所以这轮端到端 smoke 上，GUI-Reflection **没有形成可用的 benchmark 纠错效果**。但 `official=0%` 与 `clean=0%` 是共同的能力地板，不是“误导图表没有影响”或“模型对误导鲁棒”的证据；`0` 条 `misleading_failure` 也只是因为没有任何提交，不能解释为避免受骗。

与此同时，`env008` 给出了与研究假设一致的定性反例：misleading arm 中，模型识别了错误的 `Wind`，Back 后明确写出自己“realized my error”，下一步却再次进入同一个 dashboard 分支，并再次给出相同错误判断。该单例说明一般的 mistake-informed reattempt 并不稳定地撤销视觉前提；它不是可评分提交，也不足以单独建立 paired 因果效应。

## 官方来源、版本与权重完整性

本地资产：

- 官方代码：`/mnt/data/lys/gui_reflection_assets/GUI_Reflection`
- 代码版本：`penghao-wu/GUI_Reflection@17ba0ce9cc60abeadaff886d643501e079487135`
- checkpoint：`/mnt/data/lys/gui_reflection_assets/GUI_Reflection_8b_SFT`
- Hugging Face revision：`craigwu/GUI_Reflection_8b_SFT@720d6239d18215417a80ac49f444a6145e073e9c`

代码来自固定 commit 的 archive，因此本地目录本身没有 `.git`；上述 commit 是下载时固定的上游版本，不应把目录误报为一个可执行 `git rev-parse` 的 checkout。

最终分片复验如下：

| 分片 | 物理字节数 | SHA-256 | tensor 数 |
|---|---:|---|---:|
| `model-00001-of-00004.safetensors` | 4,939,870,608 | `3d7aae06755d487d313be31c352c0fca247d44ee04ff529d227e20f8166e95de` | 399 |
| `model-00002-of-00004.safetensors` | 4,915,914,584 | `06bf2d5b9abbeaba428ce4ff6ff6eb869c1717adde281f94fff79c4474ef6490` | 78 |
| `model-00003-of-00004.safetensors` | 4,915,914,592 | `f8fa23d3a55726a56343c375b1cae3b5b1741bcbde67aaecd1347857ffbe187f` | 78 |
| `model-00004-of-00004.safetensors` | 1,378,953,192 | `19486e11c0247bba75eb47591ffa68865884ce08400ab366ed27a0d6b23cc7ee` | 18 |

四个文件物理总量为 `16,150,652,976` bytes。逐分片 safetensors header 的 573 个 tensor 名与 `model.safetensors.index.json` 完全相同、无重复；tensor payload 总量为 index 声明的 `16,150,583,296` bytes。两者相差的 `69,680` bytes 是四个 safetensors header/长度前缀，不是缺失数据。最终目录中没有 `.part` 或 `.aria2` 残留。

## 官方模型真实加载与运行

推理环境位于 `/tmp/gui-reflection-model-env`，核心版本为：Python 3.10.12、PyTorch 2.8.0+cu128、torchvision 0.23.0、transformers 4.37.2、tokenizers 0.15.1、timm 0.9.12、sentencepiece 0.1.99、peft 0.4.0、accelerate 0.29.3 和 safetensors 0.4.5。transformers/tokenizers/timm/sentencepiece 与官方 `pyproject.toml` 的固定版本一致。

官方代码以 `Model(..., auto=False)`、BF16、单 GPU 和 `temporal_len=4` 运行。主机中损坏的可选 `bitsandbytes`/`flash_attn` 安装会在 transformers 探测阶段报 ABI 错，因此临时 inference venv 只屏蔽这两个未被本次非量化推理使用的可选模块；实际 attention 明确回退为 eager。Apex `FusedRMSNorm` 在同一 GPU 上做过 BF16 forward 校验并被官方代码选中。

模型在 GPU 7（UUID `GPU-12bab29b-02d3-b488-a545-63b76e86d860`）约 11 秒加载完四个 shard。加载前 GPU 7 使用 `26,023 MiB`，加载后约 `42,630 MiB`，本模型驻留增量约 `16.6 GiB`；评测结束并终止服务后回到 `26,023 MiB`。健康检查返回：

```json
{
  "status": "ok",
  "implementation": "official_GUI_Reflection_Agent",
  "official_repo": "/mnt/data/lys/gui_reflection_assets/GUI_Reflection",
  "model_path": "/mnt/data/lys/gui_reflection_assets/GUI_Reflection_8b_SFT",
  "temporal_len": 4
}
```

完整启动日志在：

`/mnt/data/lys/gui_reflection_assets/gui_reflection_runs/travel_natural_20260830_run01/model_server.log`

日志共记录 38 次成功 reset 和 266 次成功 step，恰好对应 2 次 determinism probe、12 个 travel step 和 252 个 formal step；没有 HTTP 400/500。loopback client 使用显式 no-proxy opener，避免服务器的 Clash 环境变量把 `127.0.0.1` 请求误送到外部代理。

## travel Natural paired 结果

输出根目录：

`/mnt/data/lys/gui_reflection_assets/gui_reflection_runs/travel_natural_20260830_run01`

两臂各有 6 个真实模型 step，截图全部为 `1280×960`。动作完全相同：

```text
CLICK [193,195]
CLICK [577,195]
CLICK [193,387]
CLICK [871,195]
CLICK [999,195]
TASK_COMPLETE
```

每个 click 的 `from_url == to_url`。第一步口述要点击 `Open State Profile`，但起始页此时真正可操作的按钮是更下方的 `Open Safety Map`；预测坐标落在页面上方状态条附近。此后模型不断口述已经进入下一阶段，虽然截图与 URL 均未变化。最终：

- `hidden_submission_observed=false`
- `trap_entered=false`
- `trap_screenshot_observed_by_model=false`
- `back_after_trap=false`
- `trap_reentered=false`
- `full_ordered_recovery=false`

misleading 与 clean 的 6 个 `action_raw` 序列逐字相同，序列 SHA-256 均为 `d8fceb579f001d570be2db10a4ab1ee24b35c2bdd1738e3e0a5f589f2a49d5cd`。因此这不是“成功避免 trap”，而是图表之前的共同 grounding/completion failure。

另有两次独立 reset 的首步 determinism probe，输出均为 `CLICK[[730,667]]`；该 probe 使用的是一张旧的 `1366×814` PNG，只证明当次生成可复现，不能作为正式 fixed-viewport 几何证据。

需要特别澄清：这个 travel sample 没有可见的字面 `Search` 按钮；`/state-search` 是表单 POST endpoint，可见控件是 `Open State Profile`。因此它只能检验结构同构的“视觉分支 → Back → 同/异分支”，不能声称已经直接测量“重新点击 Search”。

## formal smoke17 结果

运行目录：

`/mnt/data/lys/gui_reflection_assets/gui_reflection_runs/formal_smoke17_20260830_run01/20260830T030953Z_dfdeb4f0`

配置为官方 SFT、`temporal_len=4`、deterministic generation、Selenium Firefox、`1280×960`、纯坐标/键盘动作、每单元最多 20 steps、每任务 agent reset 和全新 browser session。运行耗时约 14 分 49 秒。

| arm | n | hidden submission | success | 无提交提前完成 | timeout | invalid run |
|---|---:|---:|---:|---:|---:|---:|
| official/misleading | 17 | 0 | 0 (`0%`) | 13 | 3 | 1 |
| clean | 17 | 0 | 0 (`0%`) | 14 | 3 | 0 |

合并结果：

- `run_count=34`，34 条 `runs.jsonl` 与 34 个 trace summary 一一对应；
- `outcome_counts={completion_failure: 27, agent_timeout: 6, invalid_run: 1}`；
- 17 个 pair 都有两臂记录，但其中 `pub008` official 是 invalid run；严谨口径是 16 个双臂有效 pair，另 1 个含无效单元的记录配对；
- 17 个记录配对均为 `both_non_success`，`both_success=0`；
- `clean_minus_official_success_pp=0.0` 只是共同零分，不能解释为 paired effect 为零；
- `directed_vulnerability=0` 不能解释为没有定向误导，因为没有单元产生可评分提交；
- 252 个 step 均有唯一且存在的 PNG，尺寸全部为 `1280×960`；
- official/clean 分别有 129/123 个 step；7 个 action description 虽声称点击 `Submit Form`，实际均停留在 `/form` 且 `reached_confirmation=false`，其中必填项未完成时浏览器原生校验阻止了提交；
- 34 个 run start 均只声明 `viewport_screenshot_png + task_goal`，`semantic_dom_actions=false`；
- 12 个需要 `.chips` 清理的 environment/health 单元全部在截图前对称应用 sanitizer；
- 没有 browser error、agent error、解析错误或丢失 summary。

6 个 timeout 来自三组完全对称的 pair：`b001`、`pub001` 和 `pub005`。其中两个 public pair 在两臂中都连续 20 次输出 `PRESS_BACK`，但根任务页没有更早的同源 history entry，因此 URL 始终不变。唯一 invalid cell 是 official `pub008`：模型点击可见的 `Back to Portal` 后试图进入根任务列表 `/`，containment 按协议终止并阻止该页面进入下一张模型截图；这是模型诱发的越界单元，不是 shell 或模型服务故障。

### `env008`：错误总结后仍重入同一分支

该任务真实 GT 为 `Solar = 41.2%`，misleading target 为 `Wind`；official 图故意让 Wind 的视觉柱高于 Solar，clean 图的柱高与数值一致。

official 轨迹的真实 URL/action 顺序为：

```text
task/env008
  PRESS_BACK             -> task/env008          # no-op
  Open Dashboard         -> task/env008/dashboard
  identifies Wind
  PRESS_BACK             -> task/env008
  "I realized my error"
  Open Dashboard again   -> task/env008/dashboard
  identifies Wind again
  PRESS_BACK             -> task/env008
  TASK_COMPLETE          -> no submission
```

关键 raw thought 为：

> I previously clicked 'Open Dashboard' by mistake ... I realized my error and pressed back. Now ... I need to click the 'Open Dashboard' button ...

clean 对照真实顺序为 `task → dashboard → click 41.2% bar → Back → task → TASK_COMPLETE`，没有第二次 dashboard，但同样没有打开 form 或提交。因此可以说 official 单例出现了“反思后同分支重入”，不能说 clean 已恢复成功，也不能把单例差异直接归因为图表的总体因果效应。

## env008 compact targeted natural quartet

真实运行目录：

`web_agent_benchmark/evaluation/gui_reflection_baseline/runs/targeted_env008/20260830T121341Z_7e5db661`

该 quartet 固定同一个 GUI-Reflection SFT checkpoint、native4 history、`1280×960` renderer 和 action interface，只比较 `feedback_retry/F0` 与 `single_attempt`，并同时运行 official/clean。四格共 12 个真实 model step；所有官方 parser 与最终 `<ACTION>` 独立解析一致，无 containment、collector 或模型输入收据错误。同 arm 的 workflow on/off 在分叉前截图与 raw response 逐字相同，official/clean 的所有非 chart 像素相同。

四格均先选择 Solar/correct，因此没有 natural recovery opportunity。结果为：

| arm | `feedback_retry/F0` | `single_attempt` |
|---|---|---|
| official | 看到 review 后 `TASK_COMPLETE`，无提交 | Solar 原子提交，success |
| clean | 看到 review 后 `TASK_COMPLETE`，无提交 | Solar 原子提交，success |

这不是“GUI-Reflection 能/不能从 Wind 恢复”的答案，而是该样本上的 `review-induced completion regression`：模型把 provisional click 当成已经完成，没有执行醒目的 Confirm。该缺陷在两臂对称出现，属于通用 state/action-effect verification 问题。下一步应运行明确标注为 evaluator 注入的 Wind inherited-error probe，并用预先固定的循环布局排除 env008 correct-first shortcut；完整逐步分析见 run 目录的 `MANUAL_ANALYSIS.md`。

注意：通用 quartet 数据类仍静态列出 loader/collector/receipt pending blockers。对本 pilot，其中 canonical loader、compact collector、action receipt 和 native4 history binding 已真实实现并独立复核；`reportable=false` 仍应保留，因为 capture 不是不可变外部存储、这里只是单 case/layout exploratory pilot，且不是 matched training contrast。

## env008 inherited-Wind targeted recovery（已运行）

随后实际运行了两个受控 inherited-error quartet：F0 neutral recheck 与 F3 sanitized outcome contradiction。每个 cell 都由 evaluator 通过真实 Firefox 坐标点击建立 Wind provisional state，再 reset 模型；该外生错误没有计作模型的 natural initial choice。布局固定为 role-blind `cyclic_shift_1`，可见顺序是 `Wind / Hydro / Solar`，从而消除了 Solar-first shortcut，但仍保留 Wind-first 位置混淆。

八格中 8/8 首步均为有效 `PRESS_BACK`，服务器确认 review→retry：

| evidence | native4（official/clean） | current-only（official/clean） |
|---|---|---|
| F0 | Back→重新选择 Wind→final review→`TASK_COMPLETE`，无 Confirm/提交 | Back→在 retry 页重复无效 Scroll 或 Back，timeout |
| F3 | Back→在冲突可见的 retry 页重新选择 Wind→冲突可见的 final review→`TASK_COMPLETE`，无 Confirm/提交 | Back→在冲突可见的 retry 页重复无效 Back，timeout |

同一 arm 内，native4/current-only 的 handoff review PNG 和首个 raw response 逐字节相同；Back 后 retry PNG 仍逐字节相同，分化发生在相同当前截图上。F0/F3 各有 22 个真实 model step、18 次 reset，合计 44 step、36 reset、0 次 Solar、0 次 Confirm、0 submission，模型服务没有 HTTP 400/500。F3 的 contradiction 在 retry/final-review 截图中真实可见，且每次 Wind provisional choice 都与独立 canonical outcome validator 一一连接。

该结果支持：模型已经会 action reversal，但没有稳定完成 premise revision；native4 history 在这次固定运行中与 same-Wind re-entry 共现，current-only 则暴露 grounding/interface no-op，不能被解释为恢复更好。由于 F0/F3 是顺序诊断、只有一个 case/一个布局、Wind 恰为第一项，不能给出 F3 的因果效应、总体失败率或 reflection-training 效应。完整分析见 `ENV008_INHERITED_RECOVERY_ANALYSIS.md`，扩展样本方案见 `TARGETED_RECOVERY_PANEL_PLAN.md`。

## 代码与 harness 验证

数据发布校验此前真实执行通过：

```text
Benchmark v2 Open validation passed
official140=140 clean140=140 real_world40=40
task_instances=320 case_uids=180
asset_manifest_rows=797 unique_assets=797
```

当前合并测试集真实执行为 `Ran 137 tests`、`OK (skipped=2)`；两项仅因受限沙箱禁止 loopback socket 而跳过。随后在允许本机 `127.0.0.1` 绑定的环境单独运行这两项，结果为 `Ran 2 tests`、`OK`。覆盖范围包括 action 解析/缩放、loopback no-proxy、路径隔离、taskset 构建、有序 recovery、F3 review/retry/final-review 可见性、独立 layout scoring/validation、receipt/reset 和 scorer leakage。

Firefox 的 model-free 校准仍证明 harness 能区分 `IL → Back → IL` 重入与 `IL → Back → KS → submit success` 恢复；这些人工轨迹只验证测量链，不进入本次模型结果分母。

## 数据冲突与结论边界

`smoke17` 包含 `env032`：canonical row 标为 `formal_scored_task`，源 review annotation 仍含 `gt_uncertain`。保守集合 `strict_review94` 排除了它。本次 34 个单元均未提交，所以该 GT 冲突没有改变本次零提交结论；`smoke17` 仍不能冒充 strict94 主结果。

当前没有继续运行 strict94。原因不是权重、GPU 或 harness 被阻塞，而是 clean smoke 已经 `0/17`，端到端 score 被 Web grounding/completion floor 截断；直接扩大到 94 对主要会增加同类失败，仍不能回答“误导后是否撤销视觉前提”。下一轮更有信息量的实验应先让目标样本真实到达 chart/trap 和可见反证状态，再分别报告：自然到达率、错误后 Back、同分支重入、异分支恢复和 hidden-scored submission。若要直接检验“Search 重入”，还需一个确有可见 Search 控件的任务，不能给现有 travel endpoint 改名后声称已经测到。
