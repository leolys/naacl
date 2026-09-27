# 接续检查与完成交付（不要重新启动已运行面板）

## 研究执行已经结束：不要重复采集、评分或调用模型

四路已于北京时间19:40:44全部结束，840终态、2236请求尝试；3个新增副本退出、0/2/3守卡恢复、原GPU7身份未变已核验。稳定快照`CAPTURE_20260927T114350560414Z.zip`（SHA256 `6f48454fafbf929279352180c58073abc6fdc5d8acf9083646516fe604fb659f`）已核验解到`captures/final_001`，正式评分/审计/补充分层在`analysis/final_001`。六版目标相合81/74/87/96/84/91；9接口失败，保留全部140分母。`REPORT.md`及`FINAL_ADVERSARIAL_REVIEW.md`已完成，终版展示为`review_final_002/OB_FULL_COMPARISON_REVIEW.html`，对应`qa_final_002/QA.json`已实际通过；001版仅作历史保留。研究部分无待执行步骤。独占打包的实际CRC/SHA回执见`OB_FULL_COMPARISON_EVIDENCE_20260927.manifest.json`，最终交付与automation-2关闭状态另见包外`CLOSEOUT.md`。本文件封存于打包前，不将预备打包误称已经成功。以下为历史执行单，不得再次运行collect/evaluate/dispatch或任何模型。

当前远端root：`/mnt/data/lys/CognitiveHijacking_CognitiveDenial/research/ob_full_comparison_20260927`；SSH别名`hexin_2007_K_root`。本地同名目录在`D:/ths_Viswork/research/`。本任务ARIS仍暂停。

专用heartbeat：`automation-2`，名称“全量六配置结果跟进”。完成交付后只删除/暂停这一项。最新已知19:12:13为2090尝试、783/840配置终态（93.2%）：775完成解析、8接口失败；四worker仍running、error为空、health均200。失败包括3条固定输出上限截断（v6/b042和pub031的VERIFY 3600 token，plain/pub018的DECIDE 700 token），以及原v3的pub003/pub006/pub011/pub015/pub019 VERIFY把输入ID `r1`输出为`R1`、被原逐字关联校验拒绝（HTTP200/finish_reason=stop）。均按协议保留，不转换ID、增大长度或补跑，不将接口失败等同于视觉判断错误。不要把这一旧快照当实时状态。最新离线审计代码已获对抗审查复核，仍须在最终稳定capture上实际执行。

1. 只读运行远端`status.py`（客户端Python：`/mnt/data/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python`，设置`PYTHONDONTWRITEBYTECODE=1`），读取4worker摘要/账本、日志、GPU状态。不得重复dispatch、重建prompt、重跑失败内容或新增样本。已有资源和2600请求上限不变。未知传输/资源变化先审证据，不能默默清账重发。
2. 未完成时保留运行，不根据部分结果调整方案。模型服务由本轮watchdog收尾，别随便停止；原GPU7永远不在清理范围。全部结束后核对`dispatch/clients_exited.json`、`cleanup_exit.json`、cleanup目录、恢复guard日志和真实进程/GPU。恢复卡如被新作业占用，跳过而不是驱逐。
3. 结束后运行远端`collect.py`，会创建新的`CAPTURE_时间.zip`并输出SHA；用scp下载唯一文件，不覆盖旧capture。用本地`receive_capture.py --archive 新zip --name final_001 --sha256 实际SHA`解到全新目录。不要使用运行中的progress_001冒充最终结果。
4. 本地Python：`D:/ths_Viswork/research/competing_rules_20260923/.venv/Scripts/python.exe`。设`PYTHONDONTWRITEBYTECODE=1`、`PYTHONIOENCODING=utf-8`；执行`evaluate.py --capture captures/final_001 --output analysis/final_001`，再`integrity_audit.py --capture captures/final_001 --output analysis/final_001/INTEGRITY.json`（从本轮目录工作或传完整路径）。严格核验账本、响应、请求、schema、图片与版本/worker归属；不为通过而改在线证据。保留所有失败、空选项和退化。
5. 沿用`/root/ob_only_adversarial`审查者，要求其核对正式统计、数据转移和代表性真实输出；只做离线审，不代替模型决策。检查是否存在只提高标签相合却给错理由；不声称全部O/B语义已人工确认。
6. 完成`REPORT.md`，主表六版各140；再列原24开发和其余116，plain/fresh-v3/历史-v3三参照分开。逐版列wrong→target、target→wrong、null/接口失败→target、target→null/失败；列实际成本、接口差异和静态任务限制。此轮是描述性全量比较，不继承旧FREEZE，不称为未见确认或网页恢复成功；不把逐题最优拼成一个新方法。
7. 用`build_review.py --capture captures/final_001 --analysis analysis/final_001 --output review_final_001`生成单文件`OB_FULL_COMPARISON_REVIEW.html`。保留完整英语真实输出，中文说明/统计/版本介绍。用headless浏览器必要QA，检查140个选项、6版卡片、图像、搜索/筛选和无外网依赖；不要因QA修改模型输出。写执行命令/测试结果/成本/剩余限制，打包原始证据和源码到唯一新ZIP，不含模型缓存或秘钥。
8. 更新`EXECUTION_STATUS.md`与`.aris/compute/hexin_2007_K_root.md`为实际终态；向用户交付结果和本地链接。完成即停，不增加第七版/新机制/新模型或额外面板。若本线程有专用于本次全量比较的heartbeat，完成交付后删除或暂停这一个，不影响其他自动任务。

## 已知无需重做的事项

- 4服务控制已通过，开跑前socket-PID及Linux互斥检查已通过。
- `RUNTIME_SEAL.json`为最终线上代码身份，运行中不得改。
- 原图/公开任务/275候选/标签均保留；env008继续保留evidence_conflict与原gold，不将Wind描述成完全无可见线索。
- 中间实时capture的文件清单与账本可能不同步，最终必须用结束后的稳定capture。已保留progress_001被汇总拒绝的记录，不是模型接口失败。
