# 先看哪里

最终独立展示：review_v3/EXPLANATION_COMPLETION_REVIEW.html。只拷贝这个 HTML 即可在其他电脑离线打开，内嵌3张原图、中文说明和全部案例JSON，不依赖项目/服务。中文为Codex离线整理，非人工确认，不调用额外API。

- REPORT_ZH.md：范围、配置、成本、逐例结果和限制。
- CLAIMS_FROM_RESULTS.md：独立同族结果复核原文，工程主张yes、语义增益partial。
- run/cases/b001、b002、pub013：各自初始集合、真实请求响应、补齐、核验、rule_state.json与重载回执。
- prompts.py / PROTOCOL.md / config.json / manifest.json：实际协议实现、配置与固定面板。
- core.py / runner.py：新版实现；旧实验代码未修改。
- tests/offline_receipt_delivery_final.xml：34项离线回归，通过不代表视觉能力。
- WIRE_AUDIT.json：真实9请求的信息隔离、图像与记账核对。
- review_v3/BROWSER_CHECK.json：离线视图浏览器检查；同目录 .html.review.json 记录页面保真审查 PASS，同族暂定判断。
- EXECUTION_LOG.md：执行命令与失败/修复记录，不含密钥。

根目录EXPLANATION_COMPLETION_REVIEW.html为保留的首版草稿，目录解析不完整。review_v2 修复目录，但源文件指纹受 Windows 换行转换影响不一致，保留 FAIL 审查记录。review_v3 修复换行并通过复核；各版本真实模型结果完全相同。最终请打开 review_v3。prepared为早期准备快照，prepared_final为启动前最终准备，均0模型调用。run/runtime_source才是实际live源快照。

总9次真实请求、0失败/重试，估算0.4324315美元；非发票。原始初始生成成本属于历史复用，不在本轮账本。三个开发样本均完成，但没有验证反问的因果收益/解释穷尽，也没有让actor使用规则完成业务提交。

复现代码需要已有Python依赖和项目内的只读API/公共输入组件，不宣称zip中的脚本可脱离这些依赖直接重新推理；HTML展示自身可完全独立。任何未来真实重跑需要新授权；不要为追求更好输出重复执行本轮。
