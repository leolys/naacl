# MisVis / OBC research collaboration handoff

这是 `leolys/naacl` 的**私有协作移交副本**，不是公开数据集发布，也不是新实验。只纳入项目所有者确认的核心材料；没有模型权重、API 密钥、SSH 私钥、守卡程序、个人账户配置、审稿/rebuttal、Real-World40 或额外任务扩展包。

## 从这里开始

1. 阅读 `docs/HANDOFF_GUIDE_ZH.md`，区分原 benchmark、当前方法与历史开发结果。
2. 原任务位于 `web_agent_benchmark/benchmark_v2_open/`：**140 条误导图任务 + 140 条正常配对任务**。图表、任务和评分答案保留；并非最新实验已经重跑了这 280 条。
3. 当前方法与历史版本位于 `research/`。最新实验为 `research/ob_full_comparison_20260927/REPORT.md`：**140 个固定单图任务 × 6 方案**，不是网页完成或轨迹恢复实验。
4. 在仓库的 `handoff-20260927-v1` Release 下载证据分包。查看 `handoff/RELEASE_ASSETS.json` 的文件清单和 SHA256；每个包可独立解压，保持相对目录。它们只补充原始请求、响应、截图和离线展示，不提供新模型运行授权。
5. 使用 `python tools/validate_handoff.py` 做无模型、无网络的移交检查；下载证据包后可用 `python tools/reproduce_latest_scores.py --assets-dir artifacts` 从真实结果重新计数。依赖和支持边界见 `environments/README.md`。

已获仓库访问权限的合作者可执行：

```bash
gh repo clone leolys/naacl
cd naacl
gh release download handoff-20260927-v1 --pattern 'naacl-evidence-part-*.zip' --dir artifacts
python tools/validate_handoff.py
python tools/reproduce_latest_scores.py --assets-dir artifacts
```

只想阅览最新140条时，无需下载全部证据：从同一Release单独下载 `OB_FULL_COMPARISON_REVIEW.html`，直接用浏览器离线打开。

## 最近完成的比较

| 方案 | 原标签相合 / 140 |
|---|---:|
| 普通直接选择 plain | 81 |
| 原 O/B 核验 v3 | 74 |
| 可见参照核验 v4 | 87 |
| 范围与条件实测 v5 | 96 |
| 逐条件核验 v6 | 84 |
| 范围决策 v7 | 91 |

全部使用 Qwen3.8-27B。840 配置单元、2236 请求尝试；失败、null 和退化未删。v5 较普通方案净增 15 条，但也有 13 条目标流失。**标签相合不是 O/B 语义核验准确率，不是网页恢复率，也不是未见任务泛化证据。** 本轮候选 O/B 来自此前生成，不新测反问的独立作用。

## 数据与模型输入隔离

原 task JSON 包含 gold、选项角色、构建说明和误导机制，属于 **benchmark 内部 spec**，不能整行交给被测模型。当前方法应沿用经过审计的公开输入投影；最新静态面板的模型可见内容位于 `research/ob_full_comparison_20260927/data/`，答案位于单独的 `offline/`。

原数据中的历史标题/目标与后续实际网页公开输入不一定相同。请阅读 `research/obc140_runtime_aligned_20260924/README_ZH.md` 与对应输入审计，不能把早期含提示的实验和修复后的实验混用。

## 版本与完整性

- 此仓库不是原 Git 历史的镜像。原始工作树、旧实验和用户未提交修改没有被更改。
- `handoff/SOURCE_PROVENANCE.json` 保存逐文件来源摘要、导出摘要、归属分包和脱敏计数；不保存凭证值。
- 旧工件中的路径、时间、状态与原哈希是**历史来源记录**，不会为了移交改写成当前运行。部分环境/守卡/敏感文件按用户要求不移交，旧全目录封存校验不能不加区分地用于此删选副本；应使用本次移交清单校验。
- 历史脚本仍保留原运行接口。没有声称每个旧在线入口已经在新电脑上完成真实推理验证，也不要直接重启旧 dispatch/服务或沿用旧预算。

数据集公开许可证与第三方图表权限尚需项目所有者确认。请保持私有，不擅自更改可见性或添加覆盖全仓库的开源许可证。保留原 `LICENSE.md` 和 `ATTRIBUTION.md`。
