# 面向误导可视化 Web Agent 的回溯与纠错方法调研

日期：2026-09-01  
范围：面向 `benchmark_v2` 的候选 agent 级回溯、验证、搜索和纠错基线。  
代码状态的含义：只把作者官方仓库中当前真实可下载的代码或权重记为“已开源”；论文写有“将开源”、空仓库或只有 README 均不算可运行实现。

## 一、结论先行

确实存在比 GUI-Reflection 更像“有深度纠错机制的 agent”的方法，但目前没有证据表明其中任何一种已经直接解决了我们的核心问题。

最值得测试的组合是：

1. **Speculative Rollback Correction，推测式分支回滚纠正**：2026 年 8 月刚更新的 Web agent 工作，也是目前与“短轨迹执行后由 reviewer 定位第一处有害偏离、重置并重放到该点、再纠正动作”最接近的开源实现。它应成为首要分支回滚基线，但论文的在线回滚发生在 teacher-assisted 数据收集阶段，最终模型在测试时并不运行该 controller；两种结果必须分开。
2. **ExACT 的反思式蒙特卡洛树搜索**：目前最强的开源 Web 搜索/回溯基线之一。它能保存分支、比较多个后继状态并回到仍可探索的状态，最适合回答“足够强的搜索是否能绕开误导分支”。
3. **BEAP-Agent 的多层深度优先回溯机制复现**：它比 BacktrackAgent 更接近真正的长距离回退，会回到最近仍有未探索动作的祖先状态并重新规划。论文已发表，但未找到官方可运行代码，因此只能做机制级复现。
4. **MobileUse 的分层反思组件**：官方代码完整。它把当前动作检查、最近轨迹检查和最终完成检查分开，分别适合诊断 `env008` 的重复重入和 `b035` 的“选对但没有确认”。它并不是真正的树搜索，所以不是深回溯的最终答案。
5. **BacktrackAgent 的单步试执行—验证—重写机制复现**：正是用户给出的 arXiv:2505.20660。它适合作为“比 GUI-Reflection 多一个显式 verifier/judger 是否就够了”的直接基线，但本质上主要是在同一时间步改写动作，不是长距离历史回滚。
6. **RoTS/GUI-RobustEval**：研究问题与我们的 targeted recovery evaluation 高度接近，特别适合借用“错误感知率、错误后成功率、错误深度 0/1/3/5”这套评测思想。不过其官方仓库截至本次核验只有 README，benchmark、数据、采样和后处理代码均标为准备中，暂时不能声称已复现 RoTS。

我们的误导可视化与这些工作的典型错误有一个决定性差异：

```text
一般 GUI 执行错误
点击未生效 / 页面未变化 / 走入死路
        ↓
后继状态直接暴露错误
        ↓
回退并尝试另一动作

我们的视觉前提错误
图表诱导出错误命题
        ↓
模型点击了与该命题一致的按钮
        ↓
点击成功、页面正常变化、局部目标看似推进
        ↓
通用 verifier 可能把错误动作判为正确
```

因此，首轮实验不能只问“最后是否成功”。它必须区分：

- **视觉前提恢复**：模型重新检查图表、否定旧命题、形成新命题并据此改选；
- **搜索式恢复**：模型没有改正图表判断，只因旧按钮被标成失败或已尝试而枚举了另一个按钮；
- **界面恢复**：只返回了可修改页面；
- **完成恢复**：选择已经正确，只补上确认或提交；
- **没有恢复或产生回归**。

如果 SRC、ExACT 或 BEAP 最终成功，但成功来自教师直接给出正确动作，或穷举剩余按钮，这说明深回溯改善任务成功率，却仍没有解决视觉前提撤销；这不是负结果，反而能更精确地界定我们下一篇论文的方法空间。

### 术语约定

- **Speculative Rollback Correction，推测式回滚纠正**：后文简称 SRC。
- **Monte Carlo Tree Search，蒙特卡洛树搜索**：通过反复扩展和估值多个动作分支来选动作；后文简称 MCTS。ExACT 的 Reflective MCTS 表示加入反思的版本，简称 R-MCTS。
- **基础模型（backbone）**：被 controller 调用、负责看图或生成动作的原始模型。
- **视觉语言模型（Vision-Language Model）**：同时接收图像和文本的模型；后文简称 VLM 时均指这一含义。
- **监督微调（Supervised Fine-Tuning）**：用输入—目标输出样本继续训练模型；后文简称 SFT。
- **过程奖励模型（Process Reward Model）**：判断中间步骤是否有助于任务的模型；后文简称 PRM。
- **controller**：组织生成、验证、搜索、回退和重新规划的 agent 控制流程，不等同于基础模型本身。
- **clean/misleading arm**：同一任务的正常图表分支与误导图表分支；不是两个不同任务。
- **环境 transition**：一次真实动作使网页从一个状态变到下一个状态。
- **takeover point**：先真实重放一段错误前缀，再让被测 agent 从该状态接管的位置。
- **All-Pass@4**：同一任务独立运行四次且四次全部成功的比例。
- **Group Relative Policy Optimization，组相对策略优化**：VeriGUI 使用的一种强化学习优化方法；后文简称 GRPO。

## 二、什么才算与本研究相关的“纠错机制”

为了避免把所有带 reflection 字样的方法混在一起，本调研按纠错对象分成六层。

| 层次 | 方法在检查什么 | 典型方法 | 对误导图表的理论上限 |
|---|---|---|---|
| 动作效果验证 | 点击是否生效，执行后页面是否符合预期 | VeriGUI、MobileUse 的当前动作反思器 | 能修复未点击、点偏、页面不变；通常看不出一个“成功生效但语义错误”的点击 |
| 单步动作重选 | 当前候选动作的后继页面是否有效、有助于任务 | BacktrackAgent | 若 verifier 能发现错误，可在原状态重选；若错误前提同时支配 verifier，则不会触发 |
| 轨迹与完成检查 | 最近几步是否循环、整体任务是否真的完成 | MobileUse、Mobile-Agent-v2 | 可减少重复进入和过早结束，但未必重新读取图表 |
| 短分支 reviewer 回滚 | 先允许执行若干步，再定位分支中第一处有害偏离并重放到那里 | Speculative Rollback Correction | 能比逐步检查更晚发现错误；reviewer 若相信误导图表，仍可能接受整条错误分支 |
| 多分支搜索与长距离回退 | 当前分支是否还有成功希望，是否应返回更早祖先状态 | ExACT、BEAP-Agent、RoTS | 能探索替代路径；仍取决于状态价值模型能否不受同一误导图表影响 |
| 视觉证据重新获取与前提更新 | 旧命题由什么证据支持，反证出现后应重查哪段图表 | ChartAgent 类工具化读图；这是我们拟研究的关键缺口 | 最有机会实现真正的视觉前提恢复，但现有方法通常不是完整 Web 恢复 agent |

这一区分也解释了为什么 GUI-Reflection 的结果不是“完全有效”或“完全无效”：它已经能在部分轨迹上完成界面回退，但没有稳定地跨过视觉命题更新、实体—动作重绑定和最终提交三个后续环节。

## 三、候选方法总表

下表按截至 2026-09-01 的官方资源状态整理。所有缩写都在表内展开说明。

| 方法 | 回溯或纠错机制 | 原论文驱动模型 | 官方代码/权重状态 | 与本任务的匹配度 | 建议 |
|---|---|---|---|---|---|
| **Speculative Rollback Correction** | 固定长度短分支执行；teacher reviewer 定位第一处有害动作；环境重置并重放到回滚点；teacher corrector 给出纠正动作；成功分支进入质量—多样性 archive | 论文只明确学生是采用 Qwen 风格 XML 工具调用的视觉语言 GUI agent；仓库支持 Qwen、Gemini、Claude、Kimi，未公开可直接核验的最终论文 checkpoint | **官方代码已开源**，MIT；仓库含 collector、reviewer、reset-and-replay、archive 和 WebArena-Infinity；未发现论文最终权重 | 很高：Web 原生、真实分支级回滚；但在线 teacher correction 是数据收集机制，不是最终测试时 agent | **第一优先审计和适配；严格分开 collector 与 trained policy** |
| **ExACT** | Reflective Monte Carlo Tree Search，反思式蒙特卡洛树搜索；分支探索、状态价值比较、回退、跨任务反思记忆 | GPT-4o；论文也把搜索轨迹蒸馏回 GPT-4o | **代码已开源**，MIT；支持 VisualWebArena/WebArena/OSWorld 分支 | 高：Web 原生、真正搜索多个状态；风险是所有 value agent 共享同一错误视觉前提 | **第一优先的开源深搜索基线** |
| **BEAP-Agent** | 把 GUI 执行建模为 Depth-First Search，深度优先搜索；Planner、Executor、Tracker 协作并做多层长距离回退 | GPT-4o 负责规划/跟踪，UI-TARS-1.5-7B 负责执行 | **未找到官方代码或权重** | 很高：最直接的深回溯假设；需要机制复现 | **第一优先的深回溯复现** |
| **MobileUse** | 当前动作、最近轨迹、全局完成三层反思；按置信度或循环条件触发 | Qwen2.5-VL-72B-Instruct，温度 0 | **代码已开源**，MIT | 中高：能分别诊断动作、循环、完成问题；没有完整搜索树 | **第一优先的开源诊断基线** |
| **BacktrackAgent** | Generator 生成动作，Verifier 做规则检查，Judger 判断任务贡献，Reflector 在原状态改写动作；每步最多反思 3 次 | Qwen2-VL-7B | ACL 页面仍写“录用后发布”，**未找到官方实现/权重** | 中高：是显式 agent 级单步纠错；但不是长距离回退 | **复现其推理机制，不复现昂贵训练** |
| **RoTS** | Robustness-driven Trajectory Synthesis，鲁棒性驱动轨迹合成；树上发现脆弱分支并合成长距离恢复数据 | 基于 Qwen2.5-VL-7B/32B 微调 | 官方仓库只有 README；评测、数据和 pipeline 均为 **In preparation** | 很高：错误深度、错误感知、错误后成功的评测与我们接近；错误源主要是 policy 自身而非外部视觉误导 | **立即借评测协议，等待官方工件后跑模型** |
| **VeriGUI** | Thinking–Verification–Action–Expectation：思考—验证—动作—预期；逐步核对预期效果与实际屏幕 | Qwen2.5-VL-3B/7B，鲁棒监督微调后再做 GRPO | **未找到官方代码或权重** | 中：非常适合“失败动作导致屏幕不变”，不适合成功导航但语义选错 | **作为预期失败的负对照** |
| **WebArbiter** | 文本生成式过程奖励模型，动态生成原则并比较多个候选动作；可用于 Best-of-N 和树搜索 | 官方开放 WebArbiter-3B/7B 等权重；搜索 policy 用 GPT-4o/mini | **代码、模型和训练数据已开源** | 中：Web 原生且适合候选重排，但输入是 accessibility tree 文本而非图表截图 | **第二阶段 verifier 对照** |
| **Mobile-Agent-v2** | Planning、Decision、Reflection、Focus 四个 agent；比较动作前后屏幕并判断错误/无效/正确 | 官方实现主要调用 GPT-4o，并配合视觉 grounding 组件 | **代码已开源** | 中：经典独立反思 agent，对长距离信念撤销仍弱 | 若 MobileUse 适配困难，用作更简单的开源替代 |
| **Agent S2** | 分层计划、逐子任务重规划和专门 grounding agent | 最佳报告配置为 Claude 3.7 Sonnet + UI-TARS-72B-DPO | **代码已开源**，Apache-2.0 | 中低：强规划框架，但没有明确的失败树、状态恢复或视觉前提撤销模块 | 只作为强通用 GUI planner，不列为主要 recovery baseline |
| **GUI-Shepherd** | GUI 过程奖励模型，对每一步给出正确性和理由，可做推理时 verifier 或训练 reward | UI-TARS-1.5-7B 类 backbone | **未找到官方代码/权重** | 中：可增强错误检测，仍需要另一个搜索/回退 controller | 后续可作为 value/verifier 替件 |
| **GUI-PRA** | 把被动过程评分改为主动调查：先合成当前判据，再用多粒度视觉工具主动找证据 | 论文报告在 Qwen-VL 系列上验证 | **未找到官方代码/权重** | 中高：可能给 reviewer 提供独立视觉证据，但本身不负责状态回退 | 作为 premise-aware verifier 候选，需防止与我们方法定位重叠 |
| **VAGEN** | 工具增强 verifier 先用轨迹表面证据，再按需探查潜在环境状态 | 论文为 agentic reward modeling 框架 | **未找到官方代码/权重** | 中高：能主动取证；仍是验证器而非恢复 controller | 与 ExACT/SRC 组合成主动取证 verifier 上界 |
| **StainFlow** | 跟踪任务相关视觉实体及其跨轨迹状态变化，并为关键节点连接高密度历史证据 | 论文用于在线强化学习过程奖励和轨迹完成判断 | **未找到官方代码/权重** | 高度相关：最接近“实体—证据跨轨迹绑定”，但没有显式错误命题撤销和网页回退 | 必须写入相关工作，并用来收紧创新点 |
| **ChartAgent** | 把图表问题分解为视觉子任务，主动裁剪、隔离柱/扇区、定位坐标轴并加标注 | 多种多模态模型可接入 | **未找到与论文对应的官方可运行仓库** | 高但角色不同：它解决“重新看清图”，不是完整 Web 回溯 | 作为“视觉证据获取上界”，不冒充通用 recovery baseline |

## 四、核心方法逐一分析

### 4.1 Speculative Rollback Correction：最新且开源的 Web 分支回滚方法

论文：<https://arxiv.org/abs/2606.12485>  
官方仓库：<https://github.com/LongkunHao/SRC_gui_agent>

Speculative Rollback Correction 的核心不是每一步都请 teacher 判断，也不是等整条轨迹失败后再复盘，而是让 student 先执行一个固定长度的短分支：

```text
student 执行最多 K 步的推测分支
    ↓
teacher reviewer 查看分支前后截图、每步动作和理由
    ↓
ACCEPT：整段保留，继续执行
ROLLBACK：返回第一处有害偏离的索引 j
    ↓
环境 reset，然后重放此前已接受的动作直到 j
    ↓
teacher corrector 在恢复后的截图上生成纠正动作
    ↓
student 从纠正后的状态继续
```

论文默认分支长度 `K=3`，最多 4 个 fork、8 个 leaf、每任务 6 次 teacher intervention；回退由 reset-and-replay 实现。分支长度实验中，`K=3` 的聚合成功率为 51.9%，平均回退 2.20 步；逐步 review 的 `K=1` 为 45.6%，而 `K=5/7` 都为 50.6%。论文据此认为太早检查会浪费 teacher，太晚检查会丢失可恢复进度。

它还把三件常被混淆的事分开：

- teacher reviewer 判断短分支是否仍保持局部进展；
- hard verifier 判断整条轨迹最终是否成功；
- quality-diversity archive 按路径长度、主要动作类型和干预次数保存多种成功解法。

论文报告最终 teacher-free 模型相对普通专家监督微调，在 WebArena-Infinity、WebArena-Lite 和一个 OSWorld 子集上分别提高 9.7、3.5、12.9 个成功率百分点；但必须注意，论文的 collector 行在执行时仍有 teacher 插入纠正，作者明确说它不能被解释成无 teacher 的测试时 policy。

官方仓库目前是真实代码仓库，不是空 README：包含 `rollout_agent.py`、`teacher_review.py`、`qd_archive.py`、视觉 agent 接口、reset-and-replay、报告工具和 WebArena-Infinity 环境。不过仓库只有一次初始提交；README 没有给出论文最终 checkpoint、student/teacher 的精确论文模型身份、已导出的 9,183 条训练样本或完整训练入口。因此“核心 collector 代码可审计”不等于“论文最终模型可直接复现”，第一步必须先做最小可运行性审计。

它对我们的价值高于 BacktrackAgent，因为 reviewer 能在三个后续步骤之后定位最早的根因；但也有三项必须控制的风险：

1. **teacher privilege**：如果 reviewer/corrector 看到隐藏答案、正确 action 或 paired clean chart，成功只是 oracle correction。它们只能看到模型可见截图、任务和已执行历史。
2. **共同视觉偏差**：如果 reviewer 与 student 都相信误导标题，reviewer 会把整条错误分支判为仍在推进。分支回滚机制根本不会启动。
3. **训练与推理混淆**：在线 collector 成功属于 teacher-assisted recovery；最终 student 是否学会自主视觉前提撤销，需要另做训练后、无 teacher 的测试，不能把两者合成一个数字。

首轮应先运行 **SRC collector-style inference probe**，即直接测试其 reviewer 能否在 `pub010/env008/b035` 上定位有害偏离；这可以快速检验机制。若 reviewer 有效，再收集少量本 benchmark rollback corrections，训练一个 matched student，比较训练前后。这比一开始就生成大规模数据更可解释。

### 4.2 BacktrackAgent：显式纠错，但主要是同一步重选

论文：<https://aclanthology.org/2025.emnlp-main.212/>  
用户给出的预印本：<https://arxiv.org/abs/2505.20660>

它的推理循环是：

```text
当前页面与历史
    ↓
Generator 产生候选动作
    ↓
执行或模拟该动作，得到后继页面
    ↓
Verifier：动作格式是否有效、页面是否发生合理变化
Judger：动作及其结果是否有助于完成任务
    ↓
通过 → 把动作写入正式轨迹
拒绝 → 回到原状态，由 Reflector 参考失败动作和前后页面改写
```

论文使用 Qwen2-VL-7B，Generator、Judger、Reflector 的监督微调各 2 个 epoch；强化学习版本再训练 Generator 和 Reflector 2 个 epoch。最大上下文长度 8192，每个时间步最多反思 3 次；训练报告使用 8 张 80GB A100。论文在 Mobile3M 上相对强基线报告任务成功率提高 7.59 个百分点。

值得注意的是，其模块本身远非完美：综合 precision（查准率）和 recall（查全率）的 F1 分数，在 Mobile3M/Auto-UI 上分别为 55.16%/60.04%；在已经检测出的错误中，按动作整体正确标准，恢复正确率分别只有 38.93%/31.24%。这说明“有 verifier + reflector”本身不等于可靠恢复。

对我们的关键判断：

- `pub010` 中，误导标题支持“下降”，点击 decline 对应按钮后页面也正常变化。规则 Verifier 会通过；如果 Judger 也相信标题，它会判断该动作有助于任务，不会触发 Reflector。
- `env008` 中，只要模型仍把视觉柱高当成正确证据，Judger 和 Reflector 可能共同重入 Wind 分支。
- 如果评测器明确告诉它“刚才的按钮错误”，Reflector 很可能改点另一个按钮；但这可能只是排除已知错误选项，不代表它撤销了错误读图命题。

因此我们应实现的是 **BacktrackAgent-style inference wrapper**，而不是在现阶段复现论文训练：

1. 在动作前保存浏览器状态；
2. 执行候选动作并保存真实后继截图；
3. 规则检查只判断动作可执行性和页面变化，不读取隐藏答案；
4. 视觉 Judger 只接收任务、截图和模型可见历史；
5. 若拒绝，恢复原状态，把失败动作及后继结果交给 Reflector；
6. 每步最多三次候选，与论文一致；
7. 单独记录“未触发纠错”“触发但仍同语义分支”“换按钮但未改视觉命题”。

该实现应在论文中命名为 **BacktrackAgent-inspired mechanism reproduction**，不能声称是官方 checkpoint 复现。

### 4.3 BEAP-Agent：目前最直接的多步长距离回退方案

论文：<https://arxiv.org/abs/2601.21352>

BEAP-Agent 明确指出：很多错误只有继续执行几步后才暴露，因此只退最后一步通常回不到真正的根因。它把 GUI 状态和动作组织成树，并按深度优先搜索执行：

```text
Planner：把任务拆成若干子任务
    ↓
Executor：把当前子任务落到真实 GUI 动作
    ↓
Tracker：更新子任务状态，并输出
         CONTINUE / BACKTRACK / FAIL / DONE
    ↓
BACKTRACK 时沿历史路径回退
    ↓
回到最近仍有未探索动作的祖先状态
    ↓
记录失败路径，Planner 重新规划
```

论文配置为 GPT-4o Planner/Tracker + UI-TARS-1.5-7B Executor，最多 50 步。在 OSWorld 上结果为 28.2%，移除回溯后为 26.3%，移除 Tracker 后为 23.6%；35.8% 的任务触发回溯，其中 65.5% 成功返回有效状态，平均回退 2.72 步。

它比 BacktrackAgent 更适合我们未来构造的深度 1/3/5 误导轨迹，例如：先根据图表选错实体，随后打开详情、填写参数、进入确认页，直到后面才收到矛盾信息。

但它仍有一个核心风险：Tracker 看到的也是原误导图表和由错误前提产生的历史。如果 Tracker 只把失败路径记成某组物理页面/坐标，而不把根因表示成“我对图表关系的判断错了”，它可能：

```text
回到图表页
    → 仍然相信同一错误命题
    → 用另一种点击路径重新进入同一语义分支
```

因此 BEAP 的结果必须同时检查“回到了多早”和“回去后信念是否变了”。

由于没有找到官方实现，建议做最小机制复现：状态栈、已失败 transition 集合、计划 ledger、Tracker、可验证的 Back 控制器和重新规划器。不要复现整套 OSWorld，也不要把我们的实现写成官方 BEAP 结果。

### 4.4 ExACT：目前最应该真正跑起来的开源深搜索基线

论文：<https://arxiv.org/abs/2410.02052>  
官方仓库：<https://github.com/microsoft/ExACT>

ExACT 的核心是 Reflective Monte Carlo Tree Search，即反思式蒙特卡洛树搜索：

- 在当前 Web 状态采样多个候选动作并扩展搜索树；
- 用 value function 评估某个状态仍然通向成功的可能性；
- 使用两个相反立场的 value 分析和一个 judge 汇总，构成多 agent 辩论；
- 根据树统计回传价值并选择下一分支；
- 对完整轨迹做错误归因，比较“预期后继状态”和“实际后继状态”，生成反思并存入向量记忆；
- 后续任务检索相关反思，避免重复类似错误。

官方代码包含 VisualWebArena/WebArena 的真实浏览器环境、搜索 agent、状态回退和树可视化。论文中 GPT-4o 驱动的 ExACT 在所报告的 Classifieds 设置上达到 32.1%，普通 GPT-4o ReAct 为 22.2%，但 token 用量约为 9.6 倍。

它是最强开源候选的原因，不是“论文总分最高”，而是它同时具备我们需要测试的三个结构：真实分支、状态恢复和独立 value 判断。

对本任务仍不能预设其会成功：

- 如果 policy、正方 value、反方 value 和 judge 都看到同一误导标题，它们可能形成一致的错误评价；多 agent 数量不会自动带来独立证据。
- 如果只有最终错误反馈才告诉搜索器某分支失败，搜索器可以遍历其他按钮而成功。这是 search recovery，不是 premise recovery。
- 当前 targeted UI 的动作空间很小，原版 ExACT 可能退化成昂贵的枚举器，因此需要增加合理 distractor、位置轮换和延迟反馈深度。

落地时建议复用 ExACT 的搜索/反思逻辑，但把其环境接口接到现有 Selenium targeted runner。由于环境和 backbone 与论文不同，结果名称应为 **ExACT R-MCTS adapter on our benchmark**。同时保留一个去掉 contrastive reflection、只做普通 MCTS 的消融，才能区分收益来自搜索还是来自反思记忆。

### 4.5 MobileUse：不够“深”，但最适合拆解现有三个失败点

论文：<https://arxiv.org/abs/2507.16853>  
官方仓库：<https://github.com/MadeAgents/mobile-use>

MobileUse 把反思分成三个时间尺度：

1. **Action Reflector，当前动作反思器**：比较动作前后截图和视觉差异，判断点击是否实现预期效果；可以按动作 token 置信度按需调用。
2. **Trajectory Reflector，最近轨迹反思器**：查看最近 3–5 步、进度摘要和动作反思，检测重复动作、重复截图和累积错误。
3. **Global Reflector，全局完成反思器**：当 Operator 想终止时查看整体历史，判断任务是否真的完成；未完成则强制继续。

论文使用 Qwen2.5-VL-72B-Instruct、温度 0。在 AndroidWorld 上，裸 Qwen2.5-VL-72B 为 35.0%，MobileUse 为 62.9%。内部消融从 Operator + Progressor 的 49.5%，依次加入动作反思、轨迹反思、全局反思后达到 55.17%、56.1%、58.6%；完整按需反思和探索后为 62.9%。论文的规模实验也表明较小模型明显更弱，因此若用 7B 适配后失败，不能直接归因于反思机制。

它与我们的样本可以形成非常清楚的逐组件假设：

| 样本 | 最可能有用的 MobileUse 组件 | 预期边界 |
|---|---|---|
| `pub010` 误导标题 | 理论上需要语义 verifier，但 Action Reflector 只看到点击成功和正常页面变化 | 大概率不触发或误判为成功 |
| `env008` 柱高与印刷值冲突 | Trajectory Reflector 可发现 Back 后重复点 Wind、重复进入同页 | 可能阻止循环，但未必重新读印刷值并选择正确实体 |
| `b035` 已改选正确但未 Confirm | Global Reflector 会发现没有真实提交 | 最有希望补上 Confirm，属于 completion recovery |

因此 MobileUse 应完整保留三个 reflector 的独立开关，并逐样本报告哪个组件起作用；不能只报“MobileUse 成功率”。Android Debug Bridge（Android 调试桥，简称 ADB）执行层不必搬来，只移植官方 reflector prompt、progress summary 和触发逻辑到现有浏览器 runner。

### 4.6 RoTS 与 GUI-RobustEval：最接近我们评测思想，但不是同一个错误来源

论文：<https://arxiv.org/abs/2605.29447>  
官方仓库：<https://github.com/AlibabaResearch/RoTS>

该工作构造了 1,216 个可执行恢复 case，覆盖 11 类 policy-induced error，即 agent 自身策略造成的错误，并设置错误深度 0、1、3、5。它把两个指标分开：

- **Error-Awareness Rate，错误感知率**：接管错误轨迹后，模型是否意识到存在错误；
- **Post-Error Success Rate，错误后成功率**：模型是否最终恢复并完成任务。

其 Robustness-driven Trajectory Synthesis 通过轨迹树在成功子树中寻找脆弱分支，并借邻近分支经验为失败子树合成恢复轨迹，总规模报告为 80 万样本。RoTS-32B 报告 OSWorld 47.4% 成功率和 33.8% All-Pass@4。

这项工作对我们有两层影响：

1. **应立即吸收的部分**：错误深度、错误感知与错误后完成分离、从同一个已执行错误前缀接管、逐错误类型分析。
2. **仍然保留的研究差异**：RoTS 的错误来自 policy 自身，如错误元素、错误目标、错误参数、误解任务、未终止等；我们的错误来自环境中的误导视觉证据，而且错误动作在局部执行上完全合法。模型需要撤销的是产生动作的视觉命题，不只是失败 transition。

官方仓库当前只有 README，并明确把 GUI-RobustEval、RoTS Dataset、Sampling Pipeline 和 Post-processing Pipeline 全部标为准备中。因此现阶段只能引用评测设计，不能把空仓库当成开源模型运行。后续应定期核验，一旦工件发布，RoTS-7B/32B 将成为必须补跑的强 learned-recovery baseline。

### 4.7 VeriGUI：可以验证为什么“动作效果纠错”不足

论文：<https://aclanthology.org/2026.acl-long.1335/>

VeriGUI 让模型每步生成 Thinking、Verification、Action、Expectation，即思考、对上一动作的验证、下一动作和下一状态预期。它用 70% 正常轨迹和 30% 合成失败恢复轨迹做 Robust SFT，再用带非对称验证奖励的 GRPO 训练。论文报告 VeriGUI-3B/7B 的恢复成功率为 51.1%/52.5%。

但作者在限制中明确说明，其 robustness benchmark 建立在“失败动作保持屏幕不变”的幂等失败假设上，不覆盖意外导航、部分状态转换或崩溃；逐步验证也不能替代长程规划。

这与我们的差异几乎是一个理想负对照：误导点击之后屏幕会按预期改变，VeriGUI 很可能输出 Verification = SUCCESS。若它失败，能证明解决低层执行不确定性的训练不能自然迁移到高层视觉语义错误；若它意外成功，再检查它是否真正重读图表。

由于没有找到官方权重，首轮只需做 TVAE 输出协议的 prompt-level ablation，不值得复现两阶段训练。

### 4.8 WebArbiter：强 Web verifier，但看不见像素级误导

论文：<https://arxiv.org/abs/2601.21872>  
官方代码与模型：<https://github.com/YaoZ720/WebArbiterCode>

WebArbiter 是一个 text-generation process reward model，即用文本生成推理的过程奖励模型。它从任务、当前页面、历史和候选动作中动态归纳 correctness、progress 等原则，对候选动作做成对比较，再用于 Best-of-N 或树搜索。官方提供 WebArbiter-3B/7B 等权重；论文在 WebArena-Lite 的 reward-guided search 中相对先前 WebPRM 最高提高 6.4 个百分点。

它的局限也与我们高度相关：论文明确把系统描述为依赖 accessibility-tree observation 的 text-based WebPRM，甚至在失败分析中指出文本 observation 缺少交互效果和细粒度 element grounding 信息。图表若是 canvas/image，其柱高、比例、截断轴和视觉注释不会自动进入 accessibility tree。

因此它应作为“很强的 Web 过程 verifier，但没有独立视觉证据”的控制：

- 只给 accessibility tree，测试它是否完全看不到图表误导；
- 再给 policy 自己生成的图表描述，测试 verifier 是否只是相信同一个错误理由；
- 最后给独立、结构化的图表证据，形成 premise-aware upper bound。

若只有第三种成功，就支持“缺的不是更强文字 judge，而是独立视觉证据获取”。

### 4.9 三个需要防止创新点重叠的主动取证/实体证据方法

这三项不是首轮 end-to-end recovery baseline，但它们比普通 reflection 更接近我们准备提出的“证据—命题—动作”链，因此相关工作不能略过。

**GUI-PRA**（<https://arxiv.org/abs/2509.23263>）把 Process Reward Agent 从一次被动打分改成主动调查。最新论文版本先根据经验合成状态相关的验证判据，再由判据指导多粒度视觉工具主动定位、解析和检查 UI 证据。它可能弥补 SRC/ExACT reviewer 的信息同源问题，但仍没有表示“旧视觉命题失效后，哪些下游 action 必须一起撤销”，也不负责真实 Back。

**VAGEN**（<https://arxiv.org/abs/2602.00575>）是工具增强的 agentic reward model：先利用轨迹里便宜、表面的证据，再按需探查环境中的潜在状态。它适合充当一个 evidence-seeking verifier，检验主动环境取证能否让 reviewer 发现语义错误；它不是完整 recovery controller。

**StainFlow**（<https://arxiv.org/abs/2606.07027>）提取可视觉验证的任务实体，跟踪这些实体及其状态沿轨迹如何变化，并围绕触发实体检索高密度历史证据。它与我们“正确实体/action 重绑定”的表述很接近。当前差异是：StainFlow主要做过程奖励和完成判断，没有显式建模误导图表中的命题支持关系、反证后的前提失效传播和网页回退。我们的创新点不能只写“跟踪实体”，而应落在**错误视觉命题的显式依赖、反证驱动的证据重取、以及由命题撤销触发的跨步 action invalidation**。

## 五、在三个代表样本上的预期分辨力

这里的“预期”是需要实验检验的假设，不是已经取得的新结果。

### 5.1 城镇游客趋势 `pub010`：错误标题造成的视觉前提劫持

已知轨迹特征：正常标题下模型能做对；误导标题下自然选择错误；同样的外部矛盾提示在正常图上能触发 Back 和改选，在误导图上不能稳定覆盖标题。

| 方法 | 可能发生什么 | 最有价值的观察 |
|---|---|---|
| Speculative Rollback Correction | student 执行 3 步后，reviewer 可能仍把标题一致的分支判为 ACCEPT | reviewer 是否在没有 hidden feedback 时定位首个错误 action；若有外部失败才回退，则属于 outcome-assisted recovery |
| MobileUse Action Reflector | 点击成功，结果页正常，因此判动作有效 | 证明动作效果验证没有触及语义前提 |
| BacktrackAgent | Verifier 通过；Judger 若相信标题也通过，Reflector不启动 | 检测失败发生在“是否触发纠错”，而非 Back 执行 |
| ExACT | 多分支搜索可能最终找到正确按钮 | 检查 value 是否先给错误分支高分；成功是否只来自终局反馈后枚举 |
| BEAP-Agent | 后续失败后可长距离退回图表页 | 退回后是否明确否定“总体下降”，还是仅避开已记忆的物理路径 |
| VeriGUI | 前后屏幕符合预期，Verification 可能为 SUCCESS | 形成低层 action-effect 方法的预期负例 |
| WebArbiter | accessibility tree 不含折线关系；容易相信候选 reasoning | 有无独立视觉证据时的差异 |

### 5.2 可再生能源 `env008`：柱高与印刷值冲突后的实体重绑定

已知轨迹特征：GUI-Reflection 在 22 条原生最近历史轨迹中 21 条完成了有效 Back，但只有 4 条碰巧重新落到正确实体，且 0 条完成提交；它容易重新进入同一 Wind 实体。

| 方法 | 可能帮助到哪一层 | 仍可能失败在哪里 |
|---|---|---|
| Speculative Rollback Correction | reviewer 可在 Wind 分支后续三步中定位最早有害动作并 reset-and-replay | teacher corrector 可能只知道“别再选 Wind”，然后靠排除法换实体 |
| MobileUse Trajectory Reflector | 发现重复页面和重复实体点击，阻止循环 | 只说“不要再点 Wind”，没有重新读取印刷值 |
| BacktrackAgent | 把已经失败的 Wind 动作交给 Reflector，重选另一按钮 | 三选一排除法会伪装成读图修复 |
| ExACT | 保留 Wind、Solar、Hydro 等分支并比较后继价值 | 小动作空间下可能靠搜索命中正确实体 |
| BEAP-Agent | 从后续详情/确认页退回实体选择页，并避免失败路径 | failed path 记录若只绑定坐标，颜色/位置轮换后可能失效 |
| premise-aware 上界 | 裁剪图表、读取印刷值、输出“最大贡献实体 = X”，再绑定按钮 | 这是我们真正希望未来方法完成的恢复链 |

`env008` 最适合增加实体名、颜色、位置和按钮顺序反事实，并把候选数扩成至少四个。这样可以区分“记住别再选 Wind”和“重新获得实体—数值关系”。

### 5.3 工厂产量 `b035`：语义已经修正，但没有真实提交

已知轨迹特征：在显式外部矛盾下，模型能够 Back 并改选正确 action，但误导版本仍会直接声明完成或反复选择，不点击 Confirm。

| 方法 | 预期作用 | 解释 |
|---|---|---|
| Speculative Rollback Correction | reviewer 把“选对但直接 terminate”定位为有害后缀，回退并由 corrector 补 Confirm | 这是分支后缀纠正和 completion recovery，不代表更强读图 |
| MobileUse Global Reflector | 看到没有提交回执，强制继续并点击 Confirm | completion recovery，不是新的视觉纠正 |
| BEAP Tracker | 子任务 ledger 中“确认提交”仍未完成，继续执行 | 说明动态进度跟踪解决最后一公里 |
| WebArbiter | 对比“宣布完成”和“点击 Confirm”，选择后者 | 过程 reward 的强项 |
| ExACT | Confirm 后到达高价值终态 | 成功主要来自终局状态估值 |

这个样本能防止我们把所有收益都写成视觉前提恢复：某方法可能只修复提交，却显著提高最终成功率。

## 六、推荐的实验不是一个总分，而是两条互补轨道

### 6.1 轨道 A：官方系统能力

能直接运行官方代码/权重的方法，尽量保留论文设置：

- Speculative Rollback Correction 官方 collector：分别报告 teacher-assisted collection-time recovery；由于未发现论文 checkpoint，最终 teacher-free policy 只有在我们按论文数据流程训练后才能报告；
- ExACT 官方搜索框架，记录实际 policy/value 模型与搜索预算；
- MobileUse 官方三层 reflector prompt 和触发逻辑，浏览器执行器替换 Android ADB；
- WebArbiter 官方 7B 过程奖励模型，作为候选动作重排器；
- RoTS 工件发布后使用官方 checkpoint 补跑。

这条轨道回答“现有公开系统拿过来能做到什么”，但模型规模、输入接口和调用预算不同，不能把差异全部归因于回溯算法。

### 6.2 轨道 B：同一 backbone 的机制控制

在同一个 screenshot-capable 视觉语言模型上只改变 controller：

1. 无 recovery 的单轨迹 policy；
2. MobileUse-style 三层 reflector；
3. BacktrackAgent-style 单步试执行与重写；
4. Speculative Rollback Correction-style 固定长度分支 reviewer 与 reset-and-replay；
5. 普通 Monte Carlo Tree Search；
6. ExACT-style 反思式 Monte Carlo Tree Search；
7. BEAP-style 多层深度优先回退。

GUI-Reflection 不能被塞进这条“只改变 controller”的因果对照，因为它是经过特定 reflection 数据训练的独立 checkpoint，不是能在同一个基础模型上开关的 wrapper。它应继续作为已经完成的外部系统基线单独报告；只有获得同训练阶段、同数据和预算、仅移除 reflection augmentation 的 matched checkpoint，才能比较 GUI-Reflection 训练本身的因果贡献。

所有条件固定：

- 同一张截图、任务文本、动作空间和浏览器状态；
- 同一基础视觉语言模型和解码温度；
- 同一最大真实环境 transition 数；
- 同时报告视觉语言模型调用数、输入/输出 token 和墙钟时间；
- verifier、planner、reflector 不得读取 hidden scorer、correct action role 或 paired clean chart；
- 若多 agent 方法使用更多调用，原样报告其计算优势，不用一个含混的“相同步数”掩盖。

机制控制 backbone 应先在 clean 版本建立任务能力。优先使用能通过 clean chart 的最强可负担 Qwen2.5-VL 规格；不建议直接把 7B 的失败写成 controller 失败，因为 MobileUse 自身报告的小模型性能明显下降。若硬件只能运行较小模型，则必须把结果限定为该模型规模下的机制测试。

## 七、首轮具体实验矩阵

### 7.1 样本

第一轮只用三个已知机制不同且有完整轨迹解释的基础任务：

| 样本 | 主要错误 | 为什么必须保留 |
|---|---|---|
| `pub010` | 误导标题持续支持错误趋势命题 | 测是否能触发语义纠错 |
| `env008` | 数值/柱高冲突后反复绑定同一实体 | 测 Back 后是否真正重读证据 |
| `b035` | 已改选正确但未 Confirm | 测 completion checker，不与读图混淆 |

每个任务保留 clean 和 misleading 两个 arm；每种方法先跑一次确定性机制轨迹，再对出现模型随机性的条件增加重复。先逐条人工审计，不急着汇总一个成功率。

第二轮再扩展到至少 6–10 个 clean-competent 基础任务，覆盖：标题冲突、截断坐标轴、反转图例、面积/长度比例失真、错误聚合、标注值与形状冲突。一个任务只有在同一 backbone 的 clean arm 能形成正确命题、正确动作并真实提交后，才进入“误导后恢复”解释；否则它只能说明基础读图能力不足。

### 7.2 错误深度

借鉴 GUI-RobustEval，为同一个根因构造四个 takeover 点：

- **深度 0**：刚做出错误 provisional choice，尚未执行后续步骤；
- **深度 1**：错误选择后已经进入一个详情或 review 状态；
- **深度 3**：基于该错误选择又完成三步正常操作；
- **深度 5**：错误前提已经传播到更深的计划和页面状态。

深度必须表示“根因动作之后已经执行的步数”，不能用 prompt 长度代替。每个 takeover state 由浏览器真实重放生成，模型接管时只看到本来可见的截图和轨迹历史。

### 7.3 每条轨迹记录的恢复链

```text
是否受到误导
  → 是否意识到旧轨迹有问题
  → 把根因定位在哪一步、哪条视觉命题
  → 实际回退了几步
  → 是否重新获取图表证据
  → 是否明确否定旧命题
  → 是否形成正确替代命题
  → 是否绑定到正确实体/action
  → 是否重新进入旧语义分支
  → 是否 Confirm 并获得真实 scorer 成功
```

建议逐条保存下列字段：

- 首次视觉命题，例如“整体下降”或“Wind 最大”；
- 首次真实点击和页面 receipt；
- error awareness 的自然语言证据；
- root-cause attribution 指向的历史 step；
- 实际 Back/restore 深度；
- 重查过的图表区域、轴、标签和数值；
- 新视觉命题及其可见证据；
- retry action、实体和坐标；
- 是否重入同一 semantic branch；
- 是否真实 Confirm/Submit；
- 最终 hidden scorer 结果；
- 总环境动作、视觉语言模型调用、token、耗时。

### 7.4 恢复结果标签

最终每个样本至少给出下面一种标签，不用一个总成功率掩盖机制：

| 标签 | 判定条件 |
|---|---|
| 真正的视觉前提恢复 | 明确否定旧图表命题，引用重新获取的可见证据，形成正确新命题，并据此改选和提交 |
| 搜索恢复但未修正前提 | 最终任务成功，但没有正确新命题；成功来自失败分支记忆、选项排除或枚举 |
| 界面回退 | 真实 Back/restore 成功，但返回后仍相信或重入旧语义分支 |
| 动作重绑定 | 命题可能已修正，且选择了正确实体/action，但尚未提交 |
| 完成恢复 | 原选择已正确，方法只补上 Confirm/Submit |
| 未恢复 | 在预算内没有离开错误分支或没有成功提交 |
| 回归 | clean 原本成功，加入 verifier/search 后被过度反思或错误改写而失败 |

## 八、必须加入的反穷举与反伪恢复控制

这是本实验能否支持论文结论的关键。

### 8.1 “只告诉旧动作错了”条件

页面只提供当前选择与独立结果不一致，不提供任何图表证据。若方法改点正确按钮，应标成 outcome-feedback-assisted recovery；不能据此声称重新读懂图表。

### 8.2 “必须陈述命题和证据”条件

retry 前要求 agent 输出：

```text
旧命题：……
旧命题为什么不再可信：……
重新检查的可见证据：……
新命题：……
新命题选择哪个 action：……
```

这只能作为诊断，不把模型自述单独当成内部因果证明；它必须和位置/实体反事实下的行为一致。

### 8.3 扩大并轮换候选动作

针对机制诊断版本，使用至少四个都合理的 action，而不是让模型在两个剩余按钮中轻易猜中。正确、误导和中性角色在位置、颜色和名称之间轮换；模型不可见 role。`env008` 还要交换实体名称与视觉位置，检查方法记住的是“Wind 失败”还是“最大印刷值对应的实体”。

### 8.4 延迟反馈

错误分支和正确分支在前几步都应产生合理、可执行的页面变化，直到深度 1/3/5 才出现矛盾。这样 action-effect verifier 不能在根节点直接靠页面没变化淘汰错误动作。

### 8.5 终局反馈消融

分别运行：

- 搜索期间可见分支失败；
- 只在最终提交后得到失败；
- 完全没有 correctness feedback，只有原图和任务。

如果 ExACT/BEAP 只在第一种或第二种成功，它依赖外部 outcome 搜索；如果第三种也能撤销命题，才更接近自主视觉前提检查。

### 8.6 verifier 独立性

同一模型扮演 policy 和 judge 可能复制同一视觉偏差。因此再加入：

- 同模型 self-judge；
- 独立 VLM judge；
- 只给 accessibility tree 的文字 judge；
- 具有 chart crop/axis/value 工具的 evidence judge。

真正要检验的不是“多叫了几个 agent”，而是 judge 是否获得了与原错误推理不同的证据通路。

## 九、建议的复现顺序与工作量

### 第一阶段：不训练模型，先回答机制问题

1. **Speculative Rollback Correction 官方代码审计与 collector adapter**
   - 先运行仓库自带最小任务，确认 reset-and-replay、reviewer 和 corrector 确实可执行；
   - 把固定长度分支接口接到 targeted Selenium 环境，先用 `K=3`；
   - reviewer/corrector 只能看到模型可见输入，禁止 hidden scorer 和 paired clean 图；
   - 把 `ACCEPT`、rollback index、reason、corrective action、真实 replay receipt 全部保留；
   - 首轮只叫 **teacher-assisted collector probe**，不能称为最终 SRC model。

2. **MobileUse reflector adapter**
   - 复用官方 prompt、触发条件和 progress summary；
   - 在现有 runner 中加入 Action、Trajectory、Global 三个独立开关；
   - 先跑 `pub010/env008/b035`，验证三个组件是否分别停在预期边界。

3. **ExACT R-MCTS adapter**
   - 复用官方搜索、value debate 和 contrastive reflection 逻辑；
   - 把 state clone/restore 和 action execution 接到 targeted Selenium 环境；
   - 同时跑 ordinary MCTS，隔离 reflection 增益；
   - 严格记录搜索树，审计是否只是遍历所有按钮。

4. **BacktrackAgent-style wrapper**
   - 按论文实现 Generator、规则 Verifier、视觉 Judger、Reflector；
   - 每一步最多三个候选；
   - 使用同一 backbone 做无 wrapper 对照；
   - 不使用隐藏正确答案训练或验证。

完成这四项后，我们已经能回答：分层反思、单步试执行重选、三步分支 review 和完整树搜索，哪一种能跨过视觉误导。

### 第二阶段：加入真正的长距离回退

5. **BEAP-style 深度优先回退**
   - 状态栈和已失败 transition 集合；
   - 计划/子任务 ledger；
   - Tracker 触发 continue/backtrack/done；
   - 回到最近还有未探索动作的祖先；
   - 在深度 0/1/3/5 上运行。

6. **WebArbiter verifier**
   - 先按官方 text-only 输入运行；
   - 再接 policy 的图表描述；
   - 最后接独立 evidence extractor，作为 verifier 输入通路消融。

### 第三阶段：只在官方工件可用后补强

7. 下载并运行 RoTS-7B/32B 与 GUI-RobustEval；在发布前不自行复现 80 万轨迹训练。
8. 若 SRC collector 在本任务上能正确定位错误，再用其纠正样本做小规模 matched supervised fine-tuning；训练后必须关掉 teacher 单独测试。
9. 若要做 learned premise recovery，再考虑合成我们自己的“误导视觉命题 → 延迟暴露 → 回退 → 重查证据 → 重绑定”训练数据。

### 为什么不先重训 BacktrackAgent 或 RoTS

- BacktrackAgent 原论文训练需要 8×A100-80GB，单次两轮微调在不同数据上报告约 25/97 小时；官方数据和 checkpoint 又未发布。
- RoTS 报告 80 万合成样本，复现成本远高于回答当前机制问题所需。
- 我们首先要知道失败是出在触发、回退、前提更新、重绑定还是提交。无训练 wrapper 已能提供这一分解；直接大规模训练可能只得到一个无法解释的总分。

## 十、推荐的首轮决策

如果只能先选一个“论文里明确实现了分支回滚且代码可见”的方法，应先审计和适配 **Speculative Rollback Correction**；如果要求的是“测试时自主搜索、没有 teacher 插入纠正”的开源 agent，则应选 **ExACT**。二者回答不同问题，不能互相替代。

如果同时考虑实现速度和机制覆盖，建议首轮按下面顺序：

```text
Speculative Rollback Correction 三步分支回滚 collector
    ↓
MobileUse 三层反思适配
    ↓
ExACT 反思式树搜索适配 + 普通树搜索消融
    ↓
BacktrackAgent 单步机制复现
    ↓
BEAP-Agent 多层长距离回退复现
    ↓
RoTS 官方工件发布后补跑
```

不过论文叙事中的比较顺序应按纠错深度呈现，而不是按实现顺序呈现：

```text
GUI-Reflection：学习过返回和换动作
    ↓
MobileUse：当前动作 / 最近轨迹 / 完成状态三层检查
    ↓
BacktrackAgent：试执行后在同一步重选
    ↓
Speculative Rollback Correction：执行短分支后定位第一处有害偏离并重放纠正
    ↓
ExACT：显式搜索多个分支并回退
    ↓
BEAP-Agent：延迟发现错误后的多层长距离回退
    ↓
我们的目标方法：回退 + 视觉证据重新获取 + 前提失效传播 + action 重绑定
```

若动作级/轨迹级方法只能提高 Back、减少循环或补上 Confirm，而 Speculative Rollback Correction、ExACT、BEAP 只能靠 teacher correction 或分支枚举成功，就能形成一个比“GUI-Reflection 不行”更强也更公平的结论：

> 现有 GUI recovery 方法覆盖了执行效果验证、局部重试和状态空间回溯，但在动作执行完全正常、错误来自误导可视化所诱导的上游命题时，恢复仍受制于错误检测与前提更新。状态回退不自动等价于认知回退；在没有独立视觉证据获取和依赖传播的情况下，成功可能来自搜索而非信念修复。

这应被当作待实验验证的研究假设，而不是在跑基线前预先写成结论。

## 十一、官方来源

- Speculative Rollback Correction 论文：<https://arxiv.org/abs/2606.12485>
- Speculative Rollback Correction 官方仓库：<https://github.com/LongkunHao/SRC_gui_agent>
- BacktrackAgent：<https://aclanthology.org/2025.emnlp-main.212/>
- ExACT 论文：<https://arxiv.org/abs/2410.02052>
- ExACT 官方仓库：<https://github.com/microsoft/ExACT>
- BEAP-Agent：<https://arxiv.org/abs/2601.21352>
- MobileUse 论文：<https://arxiv.org/abs/2507.16853>
- MobileUse 官方仓库：<https://github.com/MadeAgents/mobile-use>
- RoTS 论文：<https://arxiv.org/abs/2605.29447>
- RoTS 官方仓库：<https://github.com/AlibabaResearch/RoTS>
- VeriGUI：<https://aclanthology.org/2026.acl-long.1335/>
- WebArbiter 论文：<https://arxiv.org/abs/2601.21872>
- WebArbiter 官方仓库：<https://github.com/YaoZ720/WebArbiterCode>
- Mobile-Agent 官方仓库：<https://github.com/X-PLUG/MobileAgent>
- Agent S2 官方仓库：<https://github.com/simular-ai/Agent-S>
- GUI-Shepherd：<https://arxiv.org/abs/2509.23738>
- GUI-PRA：<https://arxiv.org/abs/2509.23263>
- VAGEN：<https://arxiv.org/abs/2602.00575>
- StainFlow：<https://arxiv.org/abs/2606.07027>
- ChartAgent：<https://arxiv.org/abs/2510.04514>
