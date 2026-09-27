# 请核查 Sol 请求被记为 Luna 的路由问题

不含密钥，可转发给网关管理员。测试日期 2026-09-07，北京时间约 20:33。

端点：`https://aimemodeldev.myhexin.com/litellm/v1/chat/completions`。

请求模型：`gpt-5.6-sol`；`reasoning_effort=medium`，`max_completion_tokens=8192`，`stream=false`；标准 system + user，多模态单图 `image_url`，detail=high。无自动 fallback，未请求 `auto` 模型。

返回：

```json
{
  "model": "gpt-5.6-sol",
  "usage": {
    "model_name": "gpt-5.6-luna",
    "prompt_tokens": 2775,
    "completion_tokens": 15,
    "ths_auto_model_request_id": "260907203345936838dca"
  }
}
```

响应 ID：`resp_0f05be575d561b8f016a9eaf2adc8487d0928c0e77a291e768`。

同一密钥 GET `/models` 能看到 Sol；GET `/model/info?model=gpt-5.6-sol` 返回四个同名配置，上游 `litellm_params.model` 均为 `gpt-5.6-sol`，但生成请求的执行记录为 Luna。

请确认：当前团队是否具备实际 Sol 权限，是否被自动路由/兜底覆盖，`usage.model_name` 是否是实际服务模型的权威字段；如不是，请给出可追踪的实际模型身份字段及此请求真实部署。我们需要可确认身份的强多模态模型做研究，不接受仅顶层回显 Sol。

本次只调用一次，已停止后续实验，未用其他模型别名逐一探测。请勿要求在反馈中公开密钥；可通过现有内部安全渠道确认所属团队。
