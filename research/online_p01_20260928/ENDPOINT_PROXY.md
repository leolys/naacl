# ENDPOINT_PROXY — 声明的基础设施差异（P0-1 在线实验）

## 背景
原 pilot（online_defense_20260925）的 actor 是 API 模型（OpenAI 兼容端点），
对 `prompts.ACTOR` 末尾的 "JSON only:" 指令原生合规（纯 JSON 输出）。
actor 引擎链（panel_core → competing_rules engine.parse_json）对非 generation
阶段是严格 `json.loads`（只剥代码围栏，不做 prose 内 JSON 提取）。

本地 actor（Qwen3.8-27B, vLLM）在默认与翻转 chat-template 两种渲染下均会
在 JSON 前输出 prose 前言，导致 proposal 阶段 `response_or_schema_failure`
（smoke_002 全部 48 单元、smoke_003 b001/b002 同因失败）。

## 处置
不改任何协议文件（prompts.py / runner.py / panel_core.py / engine.py 均原封）。
新增 `endpoint_proxy.py`：flask 转发代理（127.0.0.1:8059 → vLLM 127.0.0.1:8058），
对 `/v1/chat/completions` 载荷注入 `response_format: {"type": "json_object"}`
（vLLM 0.30 guided JSON），其余载荷与响应逐字节转发。
`config.json` 的 `endpoint` 由 8058 改为 8059。

## 差异定性
- 声明为基础设施差异（服务端结构化输出约束），不是协议/评分改动。
- 等价性论证：原 pilot 的 API actor 由服务商侧结构化输出保证 JSON 合规；
  本代理以 guided decoding 复现该保证（约束形式，不约束内容）。
- 传递性：xmodel 实验的 M1 同模型通过 runner 级 `--enable-thinking=false`
  实现同等效果；此处因 API 客户端（panel_core）密封，改为端点级实现。

## 归档
- smoke_002 → smoke_002_browserlibs_fail（浏览器系统库缺失，全单元失败）
- smoke_003 → smoke_003_actor_prose_fail（actor prose 前言，b001/b002 失败）
- 两者账本保留审计。
