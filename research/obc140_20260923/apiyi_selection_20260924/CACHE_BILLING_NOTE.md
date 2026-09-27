# APIYI GPT-5.6 缓存写入计费核查（2026-09-24）

结论：本次公开文档核查无法确认 APIYI 对 `gpt-5.6-sol`／`gpt-5.6-terra` 的缓存写入单价或倍率。记为 **unknown**，不能把普通输入／输出乘价所得金额称为实扣。此说明不修改 `provider_rates.json` 或既有原始记录。

## 一手公开文档的证据与版本边界

1. [APIYI 模型注册表](https://docs.apiyi.com/model-registry.json)列出普通输入、输出、缓存读取单价；搜索未发现 `cache_write` 或 `cache_creation` 字段。此前记录的生成时间为 `2026-09-22T22:04:36.838Z`。缺字段不等于写入免费。
2. [Sol 模型页](https://docs.apiyi.com/models/gpt-5-6-sol)与 [Terra 模型页](https://docs.apiyi.com/models/gpt-5-6-terra)的定价表只有普通输入／缓存读／输出，没有独立写入价格。两者短上下文普通输入分别为 $4／$2 每 1M tokens，适用于不超过 272,000 输入 tokens 的本文情景。
3. [APIYI OpenAI 缓存指南](https://docs.apiyi.com/api-capabilities/openai/prompt-caching)明确写“缓存写入 0×（免费）”，但正文同时说明依据的是 **2026 年 6 月数据**，示例价格表列 `gpt-5.4`、`gpt-5.4-mini`、`gpt-5.5`、`gpt-5.1`／`gpt-5`，没有列 GPT-5.6。不能把该旧版通用说明外推为 GPT-5.6 写入免费。旧机制的“写入免费”也不能解释成首次处理这些输入 tokens 免费，而是没有额外写入费用。
4. [APIYI 缓存计费 FAQ](https://docs.apiyi.com/faq/cache-billing)同样概括 OpenAI 写入免费，并指向上述指南；没有区分 GPT-5.6 后新增的写入机制。该页面不足以解决版本适用性。
5. [APIYI Claude 缓存指南](https://docs.apiyi.com/api-capabilities/claude-prompt-caching)明确列 1.25×／2× 写入倍率，但限定 Claude／Anthropic Messages API，不是 GPT-5.6 计费证据。
6. [APIYI 日志金额说明](https://docs.apiyi.com/faq/log-billing-explained)解释：响应 usage 不直接给最终金额；实际成本还受分组倍率与充值赠送影响。该页的普通输入／缓存读取／输出公式没有覆盖本例新出现的 GPT-5.6 `cache_write_tokens` 分类。

因此，即使主线程独立确认 OpenAI 官方 GPT-5.6 写入按普通输入的 125% 计费，也只能将该倍率作为网关费用的明确假设；不能自动写入 APIYI 已核实价格，更不能替代用户账户实扣证据。未发现适用文档不证明服务端一定没有实现该计费。

## 首例原始用量

只读来源：[Sol b001 proposal attempt_01.json](runs/gpt-5.6-sol/tasks/b001/proposal/round_001/attempt_01.json)。

| 字段 | 观测值 |
| --- | ---: |
| `usage.prompt_tokens`／`usage.input_tokens` | 11553 |
| `usage.completion_tokens`／`usage.output_tokens` | 110 |
| `usage.total_tokens` | 11663 |
| `usage.prompt_tokens_details.cached_tokens` | 0 |
| `usage.prompt_tokens_details.cache_write_tokens` | 11550 |

嵌套的 `usage.billing_usage.openai_usage.input_tokens_details` 也给出缓存读 0、缓存写 11550；其 `input_tokens=11553`、`output_tokens=110` 与顶层一致。这个嵌套结构中的 `prompt_tokens`／`completion_tokens` 为 0，不能据此将请求用量算成 0。嵌套 `output_tokens_details.reasoning_tokens=28`，而顶层 `completion_tokens_details.reasoning_tokens=0`，存在表示差异，应保留；不得把 28 自动再次加到输出总数 110 上。

## 只作敏感性说明的两种金额

以下都采用已有公开短上下文默认标价：普通输入 $4／1M、输出 $20／1M；缓存读为 0。所有金额均为美元，均未验证账户实扣、分组和充值折扣。

| 明确假设 | 算式 | 金额 |
| --- | --- | ---: |
| 所有输入仅按普通输入价计费，不加写入溢价 | `(11553 × 4 + 110 × 20) / 1000000` | $0.048412 |
| 缓存写入 tokens 是输入总数的子集，且它们按普通输入价 1.25×计费 | `((11553 - 11550) × 4 + 11550 × 5 + 110 × 20) / 1000000` | $0.059962 |

第二种情景比第一种高 $0.011550。它按写入分类替换相应普通输入价，**不是**在全部输入已收费后再叠加完整 1.25 倍费用。上述两值是情景，不是经证实的上下界或账单。

建议本轮报告并列保留：原始普通输入／输出总量、缓存读／写量、普通输入价参考金额、1.25×写入假设情景金额，以及 `actual_charge=unknown`／`apiyi_cache_write_rate=unknown`。若没有足够证据确定写入 token 是否包含在输入总数内，情景还应明确保留这一假设。

本核查仅读取公开文档与授权的本地 attempt 记录；没有读取账户或凭据，没有发起推理或账单请求。
