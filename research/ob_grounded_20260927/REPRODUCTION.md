# 阅览与复核，不自动重新推理

## 无依赖阅览

最终交付的 `OB_GROUNDED_REVIEW.html` 内嵌全部原图、公开任务、原O/B、核验输出及请求文字。复制这一个HTML到另一台电脑，用浏览器打开即可；不需要项目、服务器、模型或联网。ZIP是额外的复核包，不是打开HTML的前置要求。

模型消息中的图片base64在HTML文本区仅以SHA256代替，以避免重复长文本；原图显示在任务卡片，ZIP中每份 `request.json` 保留完整实际图片数据。

## 保存的运行身份

- 本地新目录：`D:/ths_Viswork/research/ob_grounded_20260927`。
- 远端新目录：`/mnt/data/lys/CognitiveHijacking_CognitiveDenial/research/ob_grounded_20260927`。
- SSH使用已有别名 `hexin_2007_K_root`，包内不含私钥或API token。
- 实际被测服务：服务器本机 `http://127.0.0.1:8058/v1`，served model name为`Qwen3.8-27B`。
- 源文件 `config.json` 固定关闭思考、temperature=0.7、top_p=0.8、top_k=20、seed=12345；同seed不保证服务输出严格确定。
- `service_snapshot/` 记录原服务配置及依赖，运行时身份以各run的preflight为准。原deployment_status时间保持原值，不假装新检查。
- 最终版本绑定于 `FREEZE.json`，包含实际开发快照的runner、schema、prompt、config和输入manifest哈希。源变化不得写回已有run。

## 离线复核命令

在解压目录中可运行以下只读分析；输出名称必须是尚不存在的新文件或目录。Python 3.9+可做大部分离线报告；真实runner另用原服务器Python环境，不要把Windows Store占位python当解释器。

```text
python audit_runs.py --runs v1_dev v2_dev v3_dev v3_confirm v3_full --output LOCAL_RECOUNT.json
python score_choices_offline.py --run v3_full --alignment ORIGINAL_LABEL_ALIGNMENT_v2.json --output LOCAL_LABEL_ALIGNMENT.json
python report.py --run v3_full --output LOCAL_VIEW --agreement LOCAL_LABEL_ALIGNMENT.json
```

上述命令不调用模型、不改标签、不执行业务提交。`audit_runs`只数模型自己的状态，不算语义准确率；`score_choices_offline`只做原选项字面映射，不执行原scorer。

全量页面可仅用包内文件重建。开发页另外有一个可选的历史C附录，会在本机仍有兄弟目录`ob_only_verification_20260926/.../provenance_map.json`时显示；那个旧附录不在本次包内，不承诺解压后还原它。开发的实际O/B、所有真实请求/响应与冻结源仍完整保留，不受该可选旧附录影响。

### 较早审查引用的 partial 路径

审查文档保留当时的快照来源名，不回写成最终运行身份。最终包不重复存放每一次 partial 的全部图像请求；相同的单元请求、响应和源快照可从 `runs/<原运行名>/<原单元>/...` 找到。例如 `full_partial03/runs/v3_full/full_b023/verify/request.json` 对应包内 `runs/v3_full/full_b023/verify/request.json`。

这不是无证据地替换路径：`SNAPSHOT_LINK_AUDIT.json` 用每份原 collector metadata 中的文件SHA逐一核对最终文件，列出实际相同的路径。原 partial metadata 也保存在包内，含原归档SHA和当时账本。核对包括不可变单元证据、运行源、source_hashes与当时preflight；仅跳过会继续变化的summary。当时的运行中summary和累计ledger不可以用最终值冒充，也不可以把多份partial的累计成本相加。完整最终账本只看 `FINAL_COSTS.json`。

可离线重新核对：`python check_snapshot_links.py --output LOCAL_SNAPSHOT_LINKS.json`。这里核对的是文件身份，不是模型结论是否正确。

实际执行命令和阶段成本见 `EXECUTION.md`、最终 `FINAL_ACCOUNTING.json` 与 `FINAL_COSTS.json`。`FINAL_ARTIFACT_AUDIT.json`核对记录身份、输入投影、归档响应和账本，而非认证内容正确。

## 如果以后要重新推理

本包不是无人值守的自动重跑器。旧配置有当晚截止时间，且现有结果不会被质量重跑；`run.py`只允许原localhost服务，并有全局请求预算和OS文件锁。截止后不要直接修改旧config来绕过限制。

新实验需要新目录、新协议/预算、明确资源权限和新结果身份；旧140结果及冻结配置不变。v1/v2的实际源分别在各自runtime_source中，不能用canonical v3的schema冒充旧版复现。

本轮没有启动模型、下载权重、占用新GPU或调用付费API。复现本包的离线分析也不需要做这些事。
