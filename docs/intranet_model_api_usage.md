# 内网模型 API 调用与测试说明

以下示例对应本项目已实测的内网网关。先用 `gpt-5.6-luna` 和短提示检查连接，再替换模型名称或提示。

## 1. 地址与访问路径

| 项目 | 值 |
|---|---|
| 网关根地址 | `https://aimemodeldev.myhexin.com/litellm` |
| 模型列表 | `GET /models` |
| Chat Completions 接口 | `POST /v1/chat/completions` |
| Anthropic Messages 格式接口 | `POST /v1/messages` |
| 鉴权 | `Authorization: Bearer <API Key>` |
| JSON 请求头 | `Content-Type: application/json` |
| Windows 本机 Clash 代理 | `http://127.0.0.1:7897` |
| 服务器经 SSH 隧道访问的代理 | `http://127.0.0.1:18891` |

服务器的调用路径是：服务器 → `127.0.0.1:18891` → SSH 反向隧道 → Windows 本机 Clash `127.0.0.1:7897` → 内网 API。

在 Windows 本机保持内网/VPN 连接，并保持下面的 SSH 进程运行：

```powershell
ssh -p 2349 -i "C:\Users\lee\.ssh\id_lys" -o ServerAliveInterval=60 -o ServerAliveCountMax=5 -N -R 127.0.0.1:18891:127.0.0.1:7897 yishengli@117.50.195.94
```

Clash 使用规则模式。此前在现有 `rules` 靠前位置添加以下规则后，服务器成功访问了 API：

```yaml
- DOMAIN,aimemodeldev.myhexin.com,DIRECT
```

这里的 `DIRECT` 是 Clash 从 Windows 本机访问内网。服务器请求仍需通过 `18891` 代理。换到另一台服务器或容器时，其 `127.0.0.1` 可能不再是这个隧道入口，需要相应建立转发。

## 2. 最方便的方式：Python 测试脚本

脚本位置：[`scripts/test_intranet_model_api.py`](../scripts/test_intranet_model_api.py)。使用 Python 3 标准库的 [`urllib.request`](https://docs.python.org/3/library/urllib.request.html)，无需安装依赖；也可将这个单文件复制到 Windows 本机运行。

以下命令在项目根目录执行。没有设置 `MODEL_API_KEY` 时，脚本会在交互终端提示隐藏输入密钥。

```bash
# 列出模型，默认走服务器代理 18891
python scripts/test_intranet_model_api.py --list-models

# Chat Completions 格式：默认测试 gpt-5.6-luna
python scripts/test_intranet_model_api.py

# 换模型、换提示
python scripts/test_intranet_model_api.py --model gpt-5.6-sol --prompt "请用一句话介绍你能做什么" --max-tokens 100

# Anthropic Messages 格式
python scripts/test_intranet_model_api.py --api messages --model claude-sonnet-4-6

# 延长网络等待时间
python scripts/test_intranet_model_api.py --model gpt-5.6-luna --timeout 120
```

Windows 本机通过 Clash 测试时，改用 `7897`；如果文件已单独复制到当前目录，去掉路径中的 `scripts/`：

```powershell
python scripts/test_intranet_model_api.py --proxy http://127.0.0.1:7897 --list-models
python scripts/test_intranet_model_api.py --proxy http://127.0.0.1:7897 --model gpt-5.6-luna

# 在本机保持内网连接时，比较直连结果
python scripts/test_intranet_model_api.py --direct --model gpt-5.6-luna
```

多次测试可以先把密钥放在当前终端的环境变量中。以下占位符需要替换成实际密钥。

```bash
# Linux / Bash
export MODEL_API_KEY='REDACTED_CREDENTIAL'
export MODEL_API_PROXY='http://127.0.0.1:18891'
```

```powershell
# Windows / PowerShell
$env:MODEL_API_KEY = 'REDACTED_CREDENTIAL'
$env:MODEL_API_PROXY = 'http://127.0.0.1:7897'
```

脚本输出以下字段：

| 字段 | 含义 |
|---|---|
| `ok` | HTTP 200 且返回模型列表或非空正文 |
| `http_status` | API 的 HTTP 状态码；连接未完成时可能没有此字段 |
| `requested_model` | 发送给网关的模型名称 |
| `response_model` | 响应顶层的模型名称，可能只是回显请求值 |
| `reported_route` | 从 `usage.model_name` 提取的网关自报路由 |
| `reply` | 模型回复正文 |
| `usage` | 网关返回的 token 使用量等信息 |
| `elapsed_seconds` | 本次请求耗时 |

每次执行只发送一个 API 请求，默认超时 90 秒，不自动重试。生成测试的默认输出上限是 64 tokens；测试较长回复时，增大 `--max-tokens`。

## 3. Linux 服务器：直接用 curl

先在当前终端设置变量：

```bash
export MODEL_API_KEY='REDACTED_CREDENTIAL'
export MODEL_API_BASE_URL='https://aimemodeldev.myhexin.com/litellm'
export MODEL_API_PROXY='http://127.0.0.1:18891'
```

获取模型列表：

```bash
curl --silent --show-error --include \
  --proxy "$MODEL_API_PROXY" --noproxy '' \
  --connect-timeout 10 --max-time 90 \
  "$MODEL_API_BASE_URL/models" \
  -H "Authorization: Bearer $MODEL_API_KEY"
```

测试 Chat Completions：

```bash
curl --silent --show-error --include \
  --proxy "$MODEL_API_PROXY" --noproxy '' \
  --connect-timeout 10 --max-time 90 \
  "$MODEL_API_BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $MODEL_API_KEY" \
  -H 'Content-Type: application/json' \
  --data-binary @- <<'JSON'
{
  "model": "gpt-5.6-luna",
  "max_tokens": 100,
  "messages": [
    {"role": "user", "content": "hello, reply in one sentence"}
  ]
}
JSON
```

测试 Anthropic Messages 格式：

```bash
curl --silent --show-error --include \
  --proxy "$MODEL_API_PROXY" --noproxy '' \
  --connect-timeout 10 --max-time 90 \
  "$MODEL_API_BASE_URL/v1/messages" \
  -H "Authorization: Bearer $MODEL_API_KEY" \
  -H 'Content-Type: application/json' \
  --data-binary @- <<'JSON'
{
  "model": "claude-sonnet-4-6",
  "max_tokens": 100,
  "messages": [
    {"role": "user", "content": "hello, reply in one sentence"}
  ]
}
JSON
```

Chat Completions 的正文通常在 `choices[0].message.content`；Messages 的正文通常在 `content` 数组的 `text` 字段。两者都要同时查看 `usage.model_name`。

JSON 中字段名是 `max_tokens`，不要写成 `max\_tokens`，URL 也不要带 Markdown 的方括号或圆括号。

## 4. Windows PowerShell：不依赖 Python 的调用示例

这组命令使用 PowerShell 的 `Invoke-RestMethod`，避免命令行 JSON 引号转义问题。代理、请求体和字符集参数已按 [Windows PowerShell 官方文档](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.utility/invoke-restmethod?view=powershell-5.1) 核对；当前环境未执行 Windows 本机测试。

PowerShell 7.4 起，`TimeoutSec` 是连接超时参数的别名；示例检测到 `OperationTimeoutSeconds` 参数时，也设置读取操作超时。[PowerShell 7 参数文档](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.utility/invoke-restmethod?view=powershell-7.6)

```powershell
$env:MODEL_API_KEY = '<你的 API Key>'
$apiBase = 'https://aimemodeldev.myhexin.com/litellm'
$apiProxy = 'http://127.0.0.1:7897'
$headers = @{ Authorization = "Bearer $env:MODEL_API_KEY" }
$requestOptions = @{
    Proxy = $apiProxy
    Headers = $headers
    TimeoutSec = 90
    UseBasicParsing = $true
}
if ((Get-Command Invoke-RestMethod).Parameters.ContainsKey('OperationTimeoutSeconds')) {
    $requestOptions.OperationTimeoutSeconds = 90
}

# 获取模型列表
$models = Invoke-RestMethod @requestOptions -Uri "$apiBase/models" -Method Get
$models.data.id

# Chat Completions
$payload = @{
    model = 'gpt-5.6-luna'
    max_tokens = 100
    messages = @(@{ role = 'user'; content = 'hello, reply in one sentence' })
} | ConvertTo-Json -Depth 6

$reply = Invoke-RestMethod @requestOptions -Uri "$apiBase/v1/chat/completions" -Method Post -ContentType 'application/json; charset=utf-8' -Body $payload
$reply.choices[0].message.content
$reply.usage.model_name

# Anthropic Messages 格式
$payload = @{
    model = 'claude-sonnet-4-6'
    max_tokens = 100
    messages = @(@{ role = 'user'; content = 'hello, reply in one sentence' })
} | ConvertTo-Json -Depth 6

$reply = Invoke-RestMethod @requestOptions -Uri "$apiBase/v1/messages" -Method Post -ContentType 'application/json; charset=utf-8' -Body $payload
$reply.content | Where-Object { $_.type -eq 'text' } | ForEach-Object { $_.text }
$reply.usage.model_name
```

若在 Windows 手动使用 curl，请写 `curl.exe`，避免 Windows PowerShell 中 `curl` 别名的差异。

## 5. 怎样判断结果

本项目在 2026-09-07 的短请求测试中观察到：

- `gpt-5.6-luna` 请求成功，网关报告的路由也为 Luna。
- 多个 GPT、Claude 和 GLM 名称都能返回 200，但网关报告的路由为 `gpt-5.6-luna` 或 `gpt-5.6-luna-back`。
- 自造且未列出的模型名也曾返回 200 并报告 Luna 路由；因此仅看 200 或响应顶层的 `model`，不足以证明调用到了指定底层模型。
- 列表中的 30 个名称返回 `401` 和 `team not allowed to access model`；模型列表可见不等于当前密钥有调用权限。
- 一些请求在 45 秒内未完成，因此本说明的默认网络等待时间使用 90 秒。超时不等同于确定不可用。

测试不同名称时建议同时变更短提示，保留 `requested_model`、`reported_route`、HTTP 状态和回复，便于区分默认路由、响应复用和权限错误。

| 现象 | 下一步 |
|---|---|
| 连接 `127.0.0.1:18891` 被拒绝 | 检查 SSH 反向隧道是否还在运行，以及当前进程是否位于同一台服务器或网络命名空间 |
| TLS EOF / `UNEXPECTED_EOF_WHILE_READING` | 检查本机内网/VPN、Clash 域名规则和 DNS；此前修正规则后恢复访问 |
| `401`，错误为 `team not allowed to access model` | 向网关管理员确认当前密钥所属团队的模型权限及名称映射 |
| `401`，其他鉴权错误 | 核对 API Key 和 `Authorization: Bearer ...` 请求头 |
| `200`，但路由名称不同 | 记录 `usage.model_name`，向管理员确认模型路由配置 |
| 超时 | 用短提示重试，或提高 `--timeout`；同时检查本机连接和网关状态 |

你提供的 Claude Code **Anthropic base URL** 是 `https://aimemodeldev.myhexin.com/litellm`。本说明验证的是上述 HTTP 文本接口；Claude Code 的工具调用、流式交互等能力需要另行测试。
