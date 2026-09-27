# 多模态 LiteLLM 接口使用说明

本文记录 `https://aimemodeldev.myhexin.com/litellm/v1` 接口的图文问答调用方式，以及已验证支持多模态输入的模型列表。用于后续跑多模态 benchmark 时统一接入方式。

## 访问前提

该域名属于公司内网域名，外部服务器通常无法直接 DNS 解析。若在内网机器上调用，可以直接访问：

```bash
https://aimemodeldev.myhexin.com/litellm/v1
```

若需要从无法访问内网的服务器调用，可在一台能访问公司内网的机器上建立 SSH 反向端口转发，把目标服务的 443 端口转发到服务器本地端口：

```cmd
ssh -p 2287 -i "C:\Users\lee\.ssh\public_2287_rsa.key" -o ServerAliveInterval=60 -o ServerAliveCountMax=5 -N -R 127.0.0.1:18443:aimemodeldev.myhexin.com:443 root@117.50.195.94
```

然后在服务器上用 `curl --connect-to` 保留原始 Host/SNI，同时把 TCP 连接导向本地转发端口：

```bash
curl --connect-to aimemodeldev.myhexin.com:443:127.0.0.1:18443 \
  -i "https://aimemodeldev.myhexin.com/litellm/v1/models" \
  -H "Authorization: Bearer $AIME_LITELLM_API_KEY" \
  -H "Content-Type: application/json"
```

注意：不要把真实 API key 写入脚本或仓库，建议通过环境变量 `AIME_LITELLM_API_KEY` 注入。

## 已验证支持图文问答的模型

以下模型已使用纯色图片做过图文输入验证，可以正确识别图片主色。测试时排除了从 URL 文本猜颜色的可能，使用的是内联 `data:image/png;base64,...` 图片。

| 模型 | 验证结果 | 备注 |
| --- | --- | --- |
| `gpt-5.2` | 支持 | 能正确识别内联图片 |
| `gpt-5.4` | 支持 | 能正确识别内联图片 |
| `gpt-5.4-mini` | 支持 | 能正确识别内联图片 |
| `gpt-5.4-nano` | 支持 | 能正确识别内联图片 |
| `gpt-5.5` | 支持 | 增大 `max_tokens` 后稳定返回答案 |
| `Doubao-Seed-2.0-pro` | 支持 | 能正确识别内联图片 |
| `qwen3.5-plus` | 支持 | 返回 usage 中包含 `image_tokens` |
| `dashscope/qwen3.5-plus` | 支持 | 返回 usage 中包含 `image_tokens` |
| `qwen3.6-plus` | 支持 | 返回 usage 中包含 `image_tokens` |
| `dashscope/qwen3.5-397b-a17b` | 支持 | 返回 usage 中包含 `image_tokens` |
| `gemini-3.1-flash-image-preview` | 支持 | 返回 usage 中包含 `image_tokens` |
| `gemini-3-pro-image-preview` | 支持 | 返回 usage 中包含 `image_tokens`；建议设置稍大的 `max_tokens` |

## 不建议作为图文问答模型使用的模型

以下模型在测试中没有稳定读图，或接口不适合作为 chat-completions 图文问答模型：

| 模型 | 现象 |
| --- | --- |
| `deepseek-v4-pro` | 请求可以返回 200，但模型提示需要上传图片，未实际读图 |
| `glm-5.1` | 提示未提供图片，未实际读图 |
| `kimi-k2.5` | 输出不稳定，未确认实际读图 |
| `kimi-k2.6` | 输出不稳定，未确认实际读图 |
| `MiniMax-M2.7` | 未确认实际读图 |
| `doubao-seedream-4-5-251128` | 不适合作为 chat-completions 文本回答模型调用 |
| `glm-5` | 测试中超时，未确认 |
| `openai/glm-5.1` | 测试时返回资源/余额错误，未确认 |

Claude 系列模型本说明未纳入清单，因为当前需求是统计 Claude 以外的图文问答模型。

## Chat Completions 调用格式

接口兼容 OpenAI Chat Completions 风格。图文消息中，`content` 使用数组，文本块为 `type: "text"`，图片块为 `type: "image_url"`。

### 内网机器直接调用

```bash
curl -i -X POST "https://aimemodeldev.myhexin.com/litellm/v1/chat/completions" \
  -H "Authorization: Bearer $AIME_LITELLM_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3.6-plus",
    "messages": [
      {
        "role": "user",
        "content": [
          {"type": "text", "text": "这张图片的主色是什么？只回答一个中文颜色词。"},
          {"type": "image_url", "image_url": {"url": "https://dummyimage.com/120x120/ff0000/ff0000.png"}}
        ]
      }
    ],
    "max_tokens": 128
  }'
```

### 通过 SSH 反向转发调用

```bash
curl --connect-to aimemodeldev.myhexin.com:443:127.0.0.1:18443 \
  -i -X POST "https://aimemodeldev.myhexin.com/litellm/v1/chat/completions" \
  -H "Authorization: Bearer $AIME_LITELLM_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3.6-plus",
    "messages": [
      {
        "role": "user",
        "content": [
          {"type": "text", "text": "这张图片的主色是什么？只回答一个中文颜色词。"},
          {"type": "image_url", "image_url": {"url": "https://dummyimage.com/120x120/ff0000/ff0000.png"}}
        ]
      }
    ],
    "max_tokens": 128
  }'
```

### Python 示例

在能直接访问公司内网域名的机器上，可以用 OpenAI SDK：

```python
import os
from openai import OpenAI

client = OpenAI(
    api_key=os.environ["AIME_LITELLM_API_KEY"],
    base_url="https://aimemodeldev.myhexin.com/litellm/v1",
)

response = client.chat.completions.create(
    model="qwen3.6-plus",
    messages=[
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "这张图片的主色是什么？只回答一个中文颜色词。"},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "https://dummyimage.com/120x120/ff0000/ff0000.png"
                    },
                },
            ],
        }
    ],
    max_tokens=128,
)

print(response.choices[0].message.content)
```

若 Python 程序运行在只能通过 `127.0.0.1:18443` 反向转发访问的服务器上，需要额外处理 DNS/SNI。最简单可靠的做法是让 benchmark 进程运行在内网机器上；否则建议先封装 `curl --connect-to`，或在网络层为 `aimemodeldev.myhexin.com:443` 提供等价的本地转发。

## Benchmark 接入建议

1. 优先使用已验证模型清单中的模型，避免使用“请求能返回 200 但没读图”的模型。
2. 图片尺寸不要太小。`qwen3.6-plus` 对 1x1 图片返回过参数错误，提示宽高需要大于 10。
3. `max_tokens` 不要设置过低。部分推理模型会先消耗 reasoning token，过低时可能导致正文为空。
4. 对每个模型先用一批 smoke test 图片做连通性验证，再跑完整 benchmark。
5. 记录 `usage.prompt_tokens_details.image_tokens`。若存在该字段，通常可以作为模型实际接收图像输入的证据之一。
6. 不要只用图片 URL 文件名或路径包含答案的样例做能力验证，模型可能从 URL 文本猜到答案。
7. 对线上评测结果保存原始响应，至少包括 `model`、`choices`、`usage`、HTTP 状态码和错误信息。

## 模型列表查询

```bash
curl -i -X GET "https://aimemodeldev.myhexin.com/litellm/v1/models" \
  -H "Authorization: Bearer $AIME_LITELLM_API_KEY" \
  -H "Content-Type: application/json"
```

通过反向转发时：

```bash
curl --connect-to aimemodeldev.myhexin.com:443:127.0.0.1:18443 \
  -i -X GET "https://aimemodeldev.myhexin.com/litellm/v1/models" \
  -H "Authorization: Bearer $AIME_LITELLM_API_KEY" \
  -H "Content-Type: application/json"
```
