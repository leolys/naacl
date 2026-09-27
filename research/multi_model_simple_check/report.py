"""Offline accounting only; reads completed artifacts, never dispatches models."""
import json
import hashlib
from collections import Counter
from pathlib import Path

from research.decision_evidence_audit.core import write_json
from .settings import CONFIGS, NAMES, RUN_ROOT, PACKAGE, REPO


def read(path):
    return json.loads(path.read_text())


def cell(value):
    return str(value).replace('|', '\\|').replace('\n', ' ')


def generate():
    wave_path = RUN_ROOT / 'wave_status.json'
    wave = {r['model']: r for r in read(wave_path)} if wave_path.exists() else {}
    lines = ['# 八任务本地多模型扩展', '',
        '本报告仅汇总本轮实际工件，不把未运行策略计成模型失败。原图、原任务、原 gold 保留。', '',
        '任务：b010、b046、health001、env035、health005、pub013、b014、env005；每模型 8 基础任务 × 2 条件 × B0/B2/B3。',
        '同模型三策略共享自然首次提交前 checkpoint。模型之间重新生成各自前缀，错误状态集合可能不同。', '',
        '沿用既有受控网页壳：任务页→图表→选择表单→真实 localhost 提交→确认。'
        '“正确完成”指在这条链路中按原主决策标签正确提交并确认，不代表原网站所有下游业务步骤或官方 GUI 完整任务成功。', '',
        '## 八个任务是什么', '',
        '| 任务 | 领域 | 公开业务目标概述 |',
        '|---|---|---|',
        '| b010 | 商业 | 根据手机品牌市场份额选择推广对象并提交 |',
        '| b046 | 商业 | 计算四周平均营收，决定第1周正常监控还是超平均跟进 |',
        '| health001 | 公共健康 | 按年度死亡负担选择需要升级跟进的年份 |',
        '| env035 | 环境 | 按每桶石油价格选择峰值年份并路由复核 |',
        '| health005 | 公共健康 | 根据检测量趋势选择后续业务团队 |',
        '| pub013 | 公共事务 | 选择最高风险州并进入优先跟进 |',
        '| b014 | 商业 | 判断产品C是否低于25,000销量阈值并选择处置 |',
        '| env005 | 环境 | 选择最大能源消费来源并提交优先监控 |', '',
        '公开任务与选项原文保存于各 TASK_MANIFEST.json 的 public_task；未重新中性化或改写它们。', '',
        '## 实际覆盖与调用成本', '',
        '| 模型 | 已启动前缀/计划16 | checkpoint | 原选择错误 | 真实提交/计划48 | 调用尝试 | 浏览器操作 | 状态 |',
        '|---|---:|---:|---:|---:|---:|---:|---|']
    cases, summaries, total_calls, total_transitions = [], {}, 0, 0
    candidates = {name:[RUN_ROOT/name, RUN_ROOT/(name+'_startup_retry01'),
                       RUN_ROOT/(name+'_action_codec_v2')] for name in NAMES}
    roots = {name:next((r for r in reversed(paths) if r.exists()), paths[0])
             for name,paths in candidates.items()}
    attempts = {}
    for name in NAMES:
        root = roots[name]
        attempts[name] = []
        for attempt_root in candidates[name]:
            if (attempt_root/'budget.json').exists():
                budget = read(attempt_root/'budget.json')
                carried = [e for e in budget['events'] if e.get('carried_from')]
                new_events = [e for e in budget['events'] if not e.get('carried_from')]
                calls_new = sum(e['kind']=='model_call' for e in new_events)
                transitions_new = sum(e['kind']=='browser_transition' for e in new_events)
                assert calls_new + sum(e['kind']=='model_call' for e in carried) == budget['model_calls']
                assert transitions_new + sum(e['kind']=='browser_transition' for e in carried) == budget['browser_transitions']
                attempts[name].append(dict(root=str(attempt_root),model_calls=calls_new,
                    browser_transitions=transitions_new, ledger_model_calls=budget['model_calls'],
                    ledger_browser_transitions=budget['browser_transitions'],
                    controls_calls=sum(e['kind']=='model_call' and '/controls/' in e['phase'] for e in new_events),
                    replay_transitions=sum(e['kind']=='browser_transition' and '/replay_' in e['phase'] for e in new_events),
                    final_status=read(attempt_root/'final_status.json') if (attempt_root/'final_status.json').exists() else None,
                    failure=read(attempt_root/'extension_failure.json') if (attempt_root/'extension_failure.json').exists() else None))
        calls = sum(a['model_calls'] for a in attempts[name])
        transitions = sum(a['browser_transitions'] for a in attempts[name])
        total_calls += calls
        total_transitions += transitions
        summary_path = root / 'evaluator/SUMMARY.json'
        if not summary_path.exists():
            lines.append(f"| {CONFIGS[name]['display']} | 未有完整结果 | 未知 | 未知 | 未知 | {calls} | {transitions} | {wave.get(name,{}).get('status','未启动')} |")
            continue
        summary = read(summary_path)
        rows = read(root / 'evaluator/CASE_TABLE.json')
        summaries[name] = summary
        cases.extend(rows)
        groups = summary['groups']
        cost = summary['costs']['experiment_actual']
        status = read(root / 'final_status.json')
        tag = '面板结束' if status['panel_completed'] else ('未通过流程/服务资格' if not status['qualification'] else '中途停止')
        if not status['qualification'] and status['model_calls']==0:
            tag = '基础设施未运行；模型控制未执行'
        lines.append('| ' + ' | '.join(map(cell, [CONFIGS[name]['display'],
            sum(g['started_prefixes'] for g in groups), sum(g['checkpoint_count'] for g in groups),
            sum(g['error_checkpoint_count'] for g in groups), sum(bool(r.get('submitted')) for r in rows),
            calls,transitions,tag])) + ' |')
    lines += ['', f'本轮真实模型尝试总计 {total_calls}；对应浏览器操作 {total_transitions}（包括控制和重放）。',
        '工程 mock 使用另一个明确标记的账本：20 次脚本化调用、48 次浏览器操作、7 次 localhost 提交；不属于真实模型结果。',
        f'真实运行与工程 mock 的已记账浏览器操作合计 {total_transitions + 48}。操作指 executor 的 navigate/execute（含失败与重放），不是截图读取或每条静态资源 HTTP 请求。',
        '服务加载、health、浏览器启动/witness 和 CUDA matmul 不算模型生成调用；模型生成尝试不因失败扣除。', '',
        'Qwen32 v2 账本携入旧非图表控制成本；此处按每个尝试的新增事件求和，既不遗漏失败，也不重复收费。', '',
        '## 全部预定任务上的正确完成', '',
        '| 模型 | 不核查 B0 | 独立全图核查 B2 | 带上下文主动核验 B3 |',
        '|---|---:|---:|---:|']
    for name, summary in summaries.items():
        reached = sum(g['checkpoint_count'] for g in summary['groups'])
        counts = [sum(s['confirmed_correct_completions'] for g in summary['groups'] for s in g['strategies']
                      if s['strategy']==strategy) for strategy in ('B0','B2','B3')]
        lines.append('| '+' | '.join([CONFIGS[name]['display'],
            *[f'{count}/16' if reached else '未运行' for count in counts]])+' |')
    lines += ['', '分母为 8 任务 × 2 条件，包含未到 checkpoint / 恢复失败；不能把未执行核验当成核验失败。', '',
        '## 按模型、图表条件和策略的结果', '',
        '| 模型 | 图表条件 | 策略 | 正确且确认完成/8 | 错误 checkpoint 恢复 | 正确→错误提交 | 正确→未提交 | B3 crop 数 |',
        '|---|---|---|---:|---:|---:|---:|---:|']
    for name, summary in summaries.items():
        for group in summary['groups']:
            arm = '误导图' if group['arm'] == 'official140' else '原对照图'
            for item in group['strategies']:
                lines.append('| ' + ' | '.join(map(cell, [CONFIGS[name]['display'], arm, item['strategy'],
                    f"{item['confirmed_correct_completions']}/8" if group['checkpoint_count'] else '未运行', item['recovery_fraction'],
                    item['correct_to_wrong'],item['correct_to_no_submit'],item['B3_crops']])) + ' |')
    lines += ['', 'B0=原提议继续；B2=独立全图目标核查；B3=带上下文的通用主动视觉核验。',
        '没有错误 checkpoint 时恢复率 N/A；不能把未到 hook、未运行核验或基础设施失败解释为核验失败。', '',
        '## 共享 checkpoint 至分支终点的转移（含 actor 续跑）', '']
    for name, summary in summaries.items():
        for strategy in ('B2','B3'):
            pieces = [s for g in summary['groups'] for s in g['strategies'] if s['strategy']==strategy]
            recovered = sum(s['recovered_from_shared_error'] for s in pieces)
            harmed = sum(s['correct_to_wrong'] for s in pieces)
            not_submitted = sum(s['correct_to_no_submit'] for s in pieces)
            invoked = sum(s['verification_executed'] for s in pieces)
            crops = sum(s['B3_crops'] for s in pieces)
            not_invoked_no_submit = sum(r['model']==name and r['strategy']==strategy
                and r.get('checkpoint_correct') is True and not r.get('submitted')
                and not r.get('verification_executed') for r in cases)
            lines.append(f'- {CONFIGS[name]["display"]} / {strategy}：实际核验 {invoked} 个状态；'
                f'错误→正确提交 {recovered}，正确→错误提交 {harmed}，已核验后的正确→未提交 {not_submitted-not_invoked_no_submit}；'
                f'另有核验未执行的正确→未提交 {not_invoked_no_submit}；crop {crops} 次。')
    lines += ['', '这些是共享 checkpoint 的配对转移，不是独立任务数或统计显著性。'
        '修改过选项但仍错误，不计为恢复；推荐正确但 actor 未完成，也不计为恢复。', '',
        '### 三种不同轨迹：回顾性展示，不作独立总体估计', '',
        '| 模型/样本/条件/策略 | checkpoint 原选择 | 核验结构化推荐及落实 | actor 最终提交 | 分支结果 |',
        '|---|---|---|---|---|',
        '| Qwen2.5 / health001 / 误导图 / B3 | 2010年升级跟进（错误） | 2018年升级跟进 | 2018年升级跟进 | 从错误恢复并真实提交 |',
        '| Qwen2.5 / b046 / 误导图 / B3 | 第1周超均值跟进（正确） | 保持第1周正常监控 | 保持第1周正常监控 | 核验改选后错误提交 |',
        '| Qwen32 / b014 / 对照图 / B3 | 产品C普通低需求复核（正确） | 仍为普通低需求复核 | 保持正常计划（错误） | actor续跑才改变选择，不能计为结构化推荐选错 |', '',
        '第三例还有必须保留的细节：核验的 option_label 保持正确，但 reason 自称柱值恰为25,000，'
        '又论证应改成正常计划，和结构化选项矛盾。后续 actor 确实改成正常计划；'
        '不能只凭 option_label 就称核验形成了“一致正确判断”，也不能据先后顺序断言 actor 因遗忘或某条理由而改选。'
        '原始理由、handoff 和 continuation 请求均保留在 qwen3_32b_action_codec_v2/online/unit_14/B3。', '',
        '## 核验已执行的配对结果', '',
        '这是条件性描述，不能取代上方按全部计划分母的端到端结果。B0 在相同且已确认完成的 unit 上配对；没有执行的核验不能被解释为方法无效。执行后的行为或动作错误仍计入，不一概当基础设施异常排除。', '',
        '| 模型 | 核验策略 | 可配对 unit 数/16 | 相同 unit 的 B0 正确完成 | 核验策略正确完成 | 未配对状态 |',
        '|---|---|---:|---:|---:|---|']
    infrastructure = {'unsupported_restore'}
    for name in summaries:
        subset = [r for r in cases if r['model']==name]
        baseline = {r['ordinal']:r for r in subset if r['strategy']=='B0'}
        for strategy in ('B2','B3'):
            arms = [r for r in subset if r['strategy']==strategy]
            paired = [r for r in arms if r.get('verification_executed') and r['status'] not in infrastructure
                      and baseline[r['ordinal']].get('confirmed_completion')]
            excluded = dict(Counter(r['status'] for r in arms if r not in paired))
            lines.append('| '+' | '.join(map(cell,[name,strategy,len(paired),
                sum(baseline[r['ordinal']]['confirmed_correct_completion'] for r in paired),
                sum(r['confirmed_correct_completion'] for r in paired),json.dumps(excluded,ensure_ascii=False)]))+' |')
    lines += ['', '## 启动与接口异常的处理', '',
        '- Qwen32 / InternVL 原尝试均在浏览器 20 秒启动等待处超时，模型生成和浏览器操作计数均为零；原失败未删除。',
        '- 独立审查后仅另存一次 120 秒启动等待的基础设施重试，未重采样已开始图表。超时具体根因仍未知。',
        '- Qwen32 重试在第 3 个非图表 Route 控制给出合法选择，却包成自拟回执；旧解析拒绝执行，共 4 调用/17 操作。',
        '- 用户另行授权 action_codec_v2：仅解开一层合法 actor action，丢弃自拟执行字段，原响应与解析 sidecar 同存。',
        '- 该 v2 仅适用于 Qwen32 本次首次图表面板；Qwen2.5 / InternVL 未按结果补跑。同输入提示但不宣称三模型完全相同的输出解析版本。',
        '- Qwen2.5 pub013 对照图 B2 恢复时公开状态一致但截图有 10 个 RGB 像素不同，严格 guard 拒绝执行核验。它是 1 条 unsupported_restore，不是模型核验失败。详见 RESTORE_NOTE.md。',
        '- InternVL env035 两条件均输出不存在的选项 Route 11986 mid-period review（真实公开选项为 Route 1986 mid-period review），未到提交 hook；不是 crop 或核验失败，也不自动替它纠正标签。', '',
        '- Qwen32 的四条未到 hook：b010 误导图在 Apple/Huawei 间交替改选至12次调用上限；env035 两条件均在 dashboard 输出 finish 而未提交；env005 误导图输出不存在的 Fossil Fuels 路由。未把这些状态替换成强制提交或错误 checkpoint。', '',
        '### 动作格式适配发生次数', '',
        '| 模型 | 阶段 | 规范化状态 | 次数 |',
        '|---|---|---|---:|']
    codec_counts = {}
    for name in NAMES:
        counts = Counter(('controls' if '/controls/' in str(p) else read(p)['phase'], read(p)['status'])
                         for p in roots[name].glob('online/**/action_codec/*.json'))
        codec_counts[name] = [dict(phase=phase,status=status,count=n) for (phase,status),n in counts.items()]
        for (phase,status),n in counts.items():
            lines.append('| '+' | '.join(map(cell,[name,phase,status,n]))+' |')
    lines += ['', 'unwrapped 是接受语法包装，不代表任何视觉判断被修改；unchanged_non_envelope 为输出原样保留。', '',
        '## 非图表控制和重放成本', '',
        '| 模型 | 控制调用（含失败） | 任务调用 | 重放浏览器操作 |',
        '|---|---:|---:|---:|']
    for name in NAMES:
        controls = sum(a['controls_calls'] for a in attempts[name])
        calls = sum(a['model_calls'] for a in attempts[name])
        replay = sum(a['replay_transitions'] for a in attempts[name])
        lines.append('| '+' | '.join(map(cell,[name,controls,calls-controls,replay]))+' |')
    lines += ['', '## 沿用的任务审核与适用性限定', '',
        '以下直接转录冻结 manifest 的既有状态/限制，不是本轮 Codex 新增人工确认。'
        '不凭 draft 字段推翻项目已有审核，不改原标签或排除任务。可见证据冲突的离线标记仍保留；这些字段未提供给在线模型。', '',
        '| 任务 | 原 readiness | 原可见证据冲突标记 | 既有限定 |',
        '|---|---|---|---|']
    for row in read(RUN_ROOT/'SOURCE_TASK_MANIFEST.json')['rows']:
        audit = row.get('evidence_audit',{})
        lines.append('| '+' | '.join(map(cell,[row['task_slug'],row.get('original_readiness','未记录'),
            audit.get('conflict','未记录'),audit.get('limits','未记录')]))+' |')
    lines += ['',
        '## 历史八任务参照（未补跑）', '',
        '以下从原 live_panel_04 的 CASE_TABLE.json 读取，不改旧结果。浏览器/运行服务器不同，仅作历史参照，不是严格同期的参数规模消融。', '',
        '| 历史 backbone | 图表条件 | B0 正确完成/8 | B2 正确完成/8 | B3 正确完成/8 |',
        '|---|---|---:|---:|---:|']
    historical = REPO / 'research/prospective_simple_check_pilot/internal_api_continuation_20260908_v1/live_panel_04/evaluator/CASE_TABLE.json'
    if historical.exists():
        old = read(historical)
        for name,label in (('M_small','Qwen3-VL-8B-Instruct'),('M_strong','历史内网 API（请求 sol，路由报告 luna/mirrorluna）')):
            for arm in ('official140','clean140'):
                counts = [sum(bool(r.get('confirmed_correct_completion')) for r in old
                    if r['model']==name and r['arm']==arm and r['strategy']==s) for s in ('B0','B2','B3')]
                lines.append('| '+ ' | '.join(map(cell,[label,'误导图' if arm=='official140' else '原对照图',*counts]))+' |')
    lines += ['', '## 实际运行模型与参数', '',
        '| 模型名称 | 加载参数总数（含视觉模块） | 精度/attention | 图像处理 |',
        '|---|---:|---|---|']
    for name in NAMES:
        path = roots[name] / 'backend_metadata.json'
        if path.exists():
            health = read(path)['health']
            lines.append('| '+' | '.join(map(cell,[CONFIGS[name]['display'],health['loaded_parameter_count'],
                health['dtype']+'/'+health['attention'],json.dumps(health['preprocessing'],ensure_ascii=False)]))+' |')
    lines += ['', 'greedy、seed=12345、max_new_tokens=1024；无量化/CPU offload。名称中的 7B/8B 不一定等于含视觉模块的实际总参数量。', '',
        '## 逐样本三层记录', '',
        '| 模型 | 任务/条件 | 策略 | checkpoint 选择 | 核验推荐 | 实际落实 | actor 最终提交 | 最终结果/状态 |',
        '|---|---|---|---|---|---|---|---|']
    for row in cases:
        final = (row.get('actor_final_submission') or {}).get('option')
        outcome = {'success':'按原评分正确', 'misleading_failure':'选择原数据集误导选项',
            'irrelevant_action_failure':'其他错误选择', 'not_submitted':'未提交'}.get(row['score']['outcome'], row['score']['outcome'])
        lines.append('| ' + ' | '.join(map(cell, [row['model'],row['task_slug']+'/'+row['arm'],row['strategy'],
            row.get('checkpoint_selection','未到 hook'), row.get('verifier_recommendation') or '无',
            row.get('executor_selection') or '无', final or '未提交',
            outcome+'/'+row['status']])) + ' |')
    lines += ['', '## 解读边界', '',
        '- 这是已用八任务的小型开发面板，不是新未见任务确认、官方 GUI 系统排名或新方法优越性实验。',
        '- B2/B3 的上下文、图像权限及调用上限不同；不能把 B3 的收益单独归因于 crop。',
        '- InternVL 与 Qwen 使用各自原生图像编码；不能声称等视觉 token/像素计算预算。',
        '- GPU 7 为用户授权共享卡，延迟受其他作业影响。旧 Qwen8 还存在跨服务器/浏览器版本差异。',
        '- 有益推荐不等于完成：必须同时检查落实选择与 actor 的真实最终提交；没有提交不能计恢复。', '',
        '- 原 scorer 的 misleading_failure 只表示选择了数据集登记的误导选项，对照图也可能出现；不能单凭这个字段认定错误由误导图造成。', '',
        '## 如何看轨迹', '',
        '每模型的 TASK_MANIFEST.json 将 unit_01..unit_16 映射到任务/图表条件。',
        '`online/unit_XX/prefix/requests` 是模型完整文本输入，`responses` 是输出，`screenshots` 是输入/执行后截图，`timeline.json` 对齐动作前后状态。',
        '`checkpoint.json` 记录未执行的真实提交提议；`B0/B2/B3` 子目录记录恢复验证、核验、后续 actor、执行回执；`server_receipts.jsonl` 是实际提交证据。',
        'evaluator/CASE_TABLE.json 和本报告末尾三层表适合先浏览，再按具体 unit 查证。', '',
        f'运行目录：`{RUN_ROOT}`', f'协议：`{PACKAGE / "PROTOCOL.md"}`']
    lines += ['', '实际采用的模型运行目录（原零派发启动失败保留在相邻目录，未重复计为任务样本）：', '']
    lines += [f'- {name}: `{root}`' for name,root in roots.items()]
    write_json(RUN_ROOT / 'ALL_CASES.json', cases)
    write_json(RUN_ROOT / 'AGGREGATE_STATUS.json', dict(real_model_call_attempts=total_calls,
        actual_browser_transitions=total_transitions, completed_reports=list(summaries),wave=wave,attempts=attempts,
        action_codec_counts=codec_counts, selected_roots={name:str(path) for name,path in roots.items()},
        status_counts=dict(Counter(r['status'] for r in cases))))
    write_json(RUN_ROOT / 'REPORT_PROVENANCE.json', dict(
        report_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        historical_source=str(historical), historical_sha256=hashlib.sha256(historical.read_bytes()).hexdigest() if historical.exists() else None,
        per_model_summaries={name:dict(path=str(roots[name]/'evaluator/SUMMARY.json'),
            sha256=hashlib.sha256((roots[name]/'evaluator/SUMMARY.json').read_bytes()).hexdigest()) for name in summaries}))
    target = RUN_ROOT / 'EXTENSION_REPORT.md'
    target.write_text('\n'.join(lines) + '\n')
    print(target)


if __name__ == '__main__':
    generate()
