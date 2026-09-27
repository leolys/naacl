"""Generate a Chinese report from actual records; no API translation or requests."""
from datetime import datetime, timezone
from pathlib import Path
import shutil
from deps import HERE, wire

STATUS={'submitted':'真实提交','actor_call_limit':'动作调用限额耗尽',
        'engineering_or_response_failure':'接口/响应失败','unresolved_public_evidence':'返回证据未解决',
        'unresolved_reverification_budget':'复核额度耗尽','global_stop':'服务或总预算停止'}


def main():
    bundle=wire.read(HERE/'EVIDENCE.json')
    notes=wire.read(HERE/'READER_NOTES_ZH.json')
    main_run=bundle['runs'][0]
    ordinary=main_run['aggregate']['ordinary']
    method=main_run['aggregate']['online_completion']
    budget=bundle['budget']
    lines=['# 同次任务内的解释补齐与规则核验：开发联调报告','',
        '日期：2026-09-25 至 2026-09-26。完整旧记录保留；本报告仅针对本轮新运行。','',
        '## 结论先行','',
        '已把方法从事后解释调整为同一次任务内、首个图表选择执行前的在线流程，并跑完固定 12 条真实 API 轨迹。工程链路存在，但当前原型的任务完成效果不理想，不能宣称已经适合直接开展全量有效性实验。','',
        f'普通 Agent：{ordinary["original_success"]}/{ordinary["runs"]} 条真实提交且原评分成功。新版方法：{method["original_success"]}/{method["runs"]} 条。方法另外包含 2 条依赖引用受阻后超时、2 条返回证据未解决、1 条提示/类型接口失败。未提交不等于防御成功。','',
        '## 方法具体如何调整','',
        '1. Agent 从原任务首页开始，自主打开仪表盘和表单。首次非空图表选项提议暂不执行；不是先做完一遍任务。',
        '2. 模型新生成完整初始解释集合。O 记录局部可见事实，B 记录有条件的解码/任务映射，C 记录推导及行动指向。',
        '3. 反问只补齐集合：可新增、细化、指出已有覆盖或保留未解决；允许零问题、零新增及同一结论的不同依据。',
        '4. 另一次模型调用逐项核验 O、B、推导，保存任务/图像内的规则状态。规则可用不等于结论正确。',
        '5. actor 收到保存后重新读取的状态，重新提出动作；执行器仍走原页面选择、必填项和真实 POST。核验器不直接代选、不自动提交。',
        '6. 后续每次 actor 调用继续收到状态与真实历史；可凭实际新证据请求有限复核。不同任务清空状态。','',
        '动作约束保留候选集合，但 actor 明确列为“支持”的链都必须受到完整核验支持。其他未确定候选仅仅存在并不会阻止动作。本轮没有通过删掉失败链或静默丢弃 actor 引用来制造提交。','',
        '## 固定配置和实验边界','',
        '- 开发样本：b001（手机推广预算）、b002（浏览器优先测试）、pub013（州风险跟进）；各含原图与原有干净图。',
        '- 两个系统分别从首页新建会话，不共享初始选择或旧解释；共 3 × 2 × 2 = 12 条新鲜轨迹。不是独立泛化样本。',
        '- APIYI `gpt-5.6-terra`，temperature=0；actor 输出上限 2400 tokens，生成 4800，核验 6000；原图原字节，无裁剪。',
        '- 每条最多 8 次 actor 调用；方法最多 4 次初始防御调用，零问题可省一次；最多一次有证据复核。传输重试最多两次尝试/调用。',
        '- actor 输入当前页面截图、已实际观察到的图表、公开页面信息与真实动作回执。核验阶段输入同一图表及公开上下文；没有隐藏正确选项、另一图表条件或历史答案。',
        '- 普通 Agent 是工作流对照，不是等总调用预算对照。方法暂停首个提议本身占用一次 actor 调用；限额对工作流余量的影响需要单独承认。',
        '- 串行、无 GPU、无训练、无 API 翻译。响应的模型名只是网关自报；没有独立证明上游身份。','',
        '## 每个条件的真实结果','',
        '| 样本 / 图表 | 普通 Agent | 新版方法 | 初始链 / 问题 / 通过结构检查的新增链 |',
        '|---|---|---|---|']
    pairs={}
    for row in main_run['rows']:
        case=row['score']['case']
        pairs.setdefault((case['task_id'],case['arm']),{})[row['score']['system']]=row
    for (task,arm),pair in pairs.items():
        first,second=pair['ordinary'],pair['online_completion']
        counts=second['counts']
        added=counts['new_chains_validated']
        lines.append(f'| {task} / {"原图" if arm=="official140" else "干净图"} | {STATUS[first["score"]["status"]]} | {STATUS[second["score"]["status"]]} | {counts["initial_chains"]} / {counts["questions"]} / {added if added is not None else "未通过接口"} |')
    lines += ['', '上表所有真实提交均由原服务器原评分判为成功；没有提交的轨迹保持无评分，不用 actor 的最后一句话代替服务器收据。b002 原图的补齐原始响应包含 2 条新增链，但整份响应未通过类型校验，不能计为有效完成核验。','',
        '## 逐样本中文导读','',notes['scope'],'']
    for key,value in notes['cases'].items():
        lines += ['### '+key.replace('_official140',' · 原图').replace('_clean140',' · 干净图'),'',
                  '**原任务：** '+value['task'],'','**初始解释：** '+value['initial'],'',
                  '**反问与补齐：** '+value['completion'],'','**实际后续：** '+value['continuation'],'',
                  '**结论边界：** '+value['boundary'],'']
    lines += ['## 调试与旧结果如何保留','',
        '- 浏览器控制中发现原生下拉框的占位文本被误当非空值。只修复 value/selected_text 投影；空值仍空、占位文本单独记录。修复前失败控制和操作成本保留。',
        '- v1 的共享提示称公开引用为“精确原文”，而校验器要求精确 JSON 类型。b002 将 true 写成字符串而失败。经审查，v2 仅改为精确 JSON 标量、保留类型；不按路径替模型补写证据，不放松校验。',
        '- b001 原图与 b002 干净图的受阻不是通过答案判定的接口 bug：actor 显式引用了未完整受支持的链。原门禁和失败记录保留，没有调提示后择优替换。','']
    if len(bundle['runs'])>1:
        debug=bundle['runs'][1]['rows'][0]
        lines += [f'单独接口复测：b002 原图 1 条，状态“{STATUS[debug["score"]["status"]]}”，新增 {debug["cost"]["request_attempts"]} 次请求。完成核验：{"是" if debug["verification"] else "否"}；保存规则版本数：{len(debug["rule_states"])}；实际服务器提交收据：{debug["score"]["server_receipt_count"]}。它属于接口调试，不替换 v1，也不并入 12 条对照结果。','']
    else:
        lines += ['单独接口复测尚未写入完成记录，不能把离线测试当真实复测结果。','']
    lines += ['## 工程验证、信息权限与原资产','',
        '- 原页面 GET/图表检查 280/280；原 HTTP 表单 POST 与确认页控制 280/280。两者都不调用模型，后者是脚本控制而非 280 条 Agent 成绩。',
        '- 三个真实浏览器控制通过；原首次失败控制保留。单元测试包含预执行 hook、零新增、旧链保留、规则范围/版本、依赖引用、预算与断点；测试通过只证明这些工程性质。',
        '- pub005 原网页有专门图片覆盖配置，实际图不等于 spec 默认图。缺失的两张图片从已有服务器只读取回、校对哈希，加入新的隔离环境副本；原本地快照和远程文件均未改动。',
        '- 逐个核对请求归档中的实际文本、图像字节、真实历史前缀和 selected flags；核验推荐、actor 提议、实际选中、真实提交分层保存。',
        '- 原图自身的文字与干净图字幕原样保留，因此不声称图表条件完全盲化。模型自己生成的疑问不覆盖既有人工审核或 gold。',
        '- v1 已记录的源文件哈希保持不变；早期快照未穷尽传递导入的格式/用量辅助文件。v2/批量入口另补这些实际导入源，不给 v1 追写身份。','',
        '## 成本','',
        f'本轮当前合计：{budget["request_attempts"]}/160 次真实请求尝试，{budget["browser_operations"]}/600 次实际浏览器操作，估算 ${budget["estimated_ledger_usd"]:.4f}/$10；实际账单未知。所有失败、调试和真实浏览器控制均计入同一本账。没有新下载模型，没有使用 GPU。','',
        '独立列账的离线本机 Flask 控制：两次 280 条 GET 审计（各 1120 次 HTTP GET）、280 条提交控制（1400 次 HTTP 操作），以及缺失资产定位中的少量 GET；不把它们计作模型运行或实际浏览器动作。估算价格沿用已授权的历史输入/输出系数，不是供应商现价或费用保证。','',
        '## 能否大规模运行','',
        '工程上：提供覆盖 140 原任务 × 2 条件、两系统共 560 条计划轨迹的配置与串行入口。全局账本、失败保留、未知请求停止、已结束跳过与半条轨迹拒绝自动重放均有检查。准备文件不是运行授权；模板预算为空，不会继承本轮额度。','',
        '研究上：当前不建议直接把该原型用于全量“证明有效”的实验。需要先明确是否缩小到视觉解释的条件、如何避免把附加流程或无任务要求的时效/唯一性问题当作必要证据，以及如何在不静默忽略真实依赖的前提下表达独立支持。后续变化须独立版本与预先固定面板，不继续围绕答案调参。','',
        '本轮只支持在线生命周期已经实现、至少一条方法轨迹真实完成，以及上述明确失败模式。没有证明总体收益、反问覆盖充分性、纠错率、长程持久化收益或方法优越性。完整调用受限开发面板不应作统计推断。','',
        '## 文件入口','',
        '- `METHOD_REVISED_ZH.md`：新方法说明；`PROTOCOL.md`：冻结 v1 协议；`prompts.py` / `prompts_v2.py`：通用提示。',
        '- `EVIDENCE.json`：逐条输入、初始集合、反问、补齐、核验、规则状态、actor 动作与真实回执。',
        '- `live_v1/`：完整 12 条请求、响应、页面截图、私有原评分收据与源快照。',
        '- `live_v2_schema_debug/`：单次独立类型接口调试，不覆盖 v1。',
        '- `batch_main.py`、`batch_config.template.json`、`README_RUN.md`：准备、运行与断点命令。',
        '- `reviews/`：同模型家族的独立线程审查，属临时审查意见，不是人工审核。','',
        '本轮结束后停止，不启动 140 对、不扩大预算、不把失败重试到成功。','']
    text='\n'.join(lines)
    versioned=HERE/'REPORT_20260926_001.md'
    if versioned.exists() and versioned.read_text(encoding='utf-8')!=text:
        raise ValueError('versioned_report_exists_choose_new_version')
    versioned.write_text(text,encoding='utf-8')
    shutil.copy2(versioned,HERE/'REPORT.md')
    print('Generated',versioned.name)


if __name__=='__main__':main()
