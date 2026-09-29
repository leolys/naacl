# FORMAL_RESULT — P0-1 在线状态化实验正式结果定稿（owner 决策 2026-09-29）

## 决策
owner 在 ScienceGuru 会话中批准（"执行选项1和选项2"）：
- **正式主结果 = batch_api_terra_002**（C 批：actor gpt-5.6-terra，严格协议、
  零引导，经 chatanywhere.tech 中转 api.chatanywhere.tech，与原 pilot
  同款模型，pilot 保真度最高）。
- **A 批（smoke_008，27B 严格）与 B 批（batch_guided_002，27B + endpoint
  proxy v2.1 json_schema 引导）作为"接口严苛性分解"分析材料**：结构约束
  可被 schema 引导修复（actor 结构失败 3→0），语义契约（精确公共叶子值、
  动态链引用、问题-响应计数耦合）不可被任何 response_format 表达，
  是 method 臂失败的绑定约束。

## C 批正式数字（48/48 单元）
- ordinary：18/24 正确（75.0%），0 错误提交，5 弃答（unresolved_public_evidence），
  1 工程失败（TargetClosedError 浏览器瞬时故障）
- method 臂（online_completion）：8/24 正确（33.3%），0 错误提交，
  12 弃答 + 1 unresolved_reverification_budget，4 工程失败
- 提交精度 26/26 = 100%；配对（ordinary vs method）：ordinary 胜 10 /
  method 胜 0 / 平 14
- 与原 pilot（gpt-5.6-terra via apiyi，n=6：ordinary 5/6、method 1/6）方向一致
- 用量：322 请求尝试 / 242 浏览器操作 / 1,796,559 input + 129,258 output tokens；
  网关未回传计费（budget 记 0，实际扣费由 owner 在网关后台核对）

## 声明的基础设施差异
1. A/B 批 actor = 本地 Qwen3.8-27B vLLM + 本地 endpoint proxy（8059→8058），
   按 ENDPOINT_PROXY.md 声明：A 批注入 response_format json_object，
   B 批按 phase 注入 json_schema（仅镜像 sealed core 硬结构规则）。
2. 三批安全预算相对原 pilot 有余量（timeout 120→600s、max_request_attempts
   160→1600、max_browser_operations 600→2400），模型/温度/相位 token 上限/
   max_actor_calls 8/max_reverification 1/interface_version typed_scalars_v2
   与 pilot 一致。
3. C 批不经过 proxy，请求直达网关（与原 pilot 同构）。

## 稳定性验证
AUTHORIZATION_API_STABILITY.json 授权 batch_api_terra_003 重跑 C 批一次
（同配置 temperature 0），用于单元级稳定性对照。
