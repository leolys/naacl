"""Read actual local artifacts and summarize; makes no API calls."""
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import json
import sys
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / 'apiyi_selection_20260924'))
import panel_core as core
import analyze_usage as costs


def summarize():
    review = core.read(HERE / 'review_data_zh.json')
    rows = review['tasks']
    budget = core.read(HERE / 'run/budget.json')
    rates = {row['modelID']: row for row in core.read(HERE.parent / 'apiyi_selection_20260924/provider_rates.json')['rates']}
    attempts = []
    for event in budget['events']:
        path = Path(event['folder']) / ('attempt_%02d.json' % event['attempt'])
        if path.is_file():
            attempts.append(costs.attempt_record(path, HERE, 'gpt-5.6-terra', event['task_slug'],
                                                 event['phase'], rates['gpt-5.6-terra']))
    accounting = costs.summarize_attempts(attempts)
    accounting.update(ledger_attempts=budget['request_attempts'],
        ledger_estimated_usd=budget['estimated_ledger_usd'],
        missing_attempt_metadata=budget['request_attempts'] - len(attempts),
        reused_historical_calls_excluded=True,
        attempt_event_identities=[{k: event[k] for k in ('task_slug','phase','round','attempt')}
                                  for event in budget['events']],
        attempts=attempts)
    accounting['requested_model_counts'] = dict(Counter(row.get('requested_model') or 'unknown' for row in attempts))
    accounting['response_model_counts'] = dict(Counter(row.get('response_model') or 'unknown' for row in attempts))
    accounting['retry_attempts'] = sum(isinstance(row.get('attempt'), int) and row['attempt'] > 1 for row in attempts)
    accounting['model_identity_issues'] = [{'file': row['file'], 'issues': row['issues']}
                                         for row in attempts if row['issues']]
    accounting['usage_alias_resolution_counts'] = dict(Counter(
        conflict['resolution'] for row in attempts for conflict in row['normalized_usage']['conflicts']))
    accounting['unresolved_usage_alias_conflicts'] = accounting['usage_alias_resolution_counts'].get('unresolved_distinct_positive_values', 0)
    accounting['usage_normalization_error_attempts'] = sum(bool(row['normalized_usage']['errors']) for row in attempts)
    core.dump(HERE / 'cost_summary.json', accounting)
    failed = [{'task': row['task_slug'], 'phase': phase, 'status': status,
               'error': row.get('stages', {}).get(phase, {}).get('error_category')}
              for row in rows for phase, status in row['status'].items()
              if status in ('failed','invalid','blocked')]
    chain_counts = Counter(len((row.get('normalized') or {}).get('chains', [])) for row in rows)
    different = sum(len({chain.get('option_label') for chain in (row.get('normalized') or {}).get('chains', [])}) > 1
                    for row in rows)
    domains = dict(Counter(row['domain'] for row in rows))
    domain_labels = {'business47': '商业', 'environment35': '环境', 'health19': '健康', 'public39': '公共事务'}
    domains_zh = '、'.join('%s %s 条' % (domain_labels.get(name, name), count) for name, count in domains.items())
    raw_chain_tasks = 0
    for row in rows:
        candidate = row.get('generated') or row.get('generation_invalid_raw') or {}
        raw_chain_tasks += int(isinstance(candidate, dict) and bool(candidate.get('chains')))
    decision_changes = Counter()
    for row in rows:
        if row['status']['verification'] != 'completed':
            continue
        recommendation = row['verification'].get('recommendation')
        original = row['proposal']['action']['option']
        decision_changes['no_recommendation' if recommendation is None else
                         'same_as_proposal' if recommendation == original else 'different_from_proposal'] += 1
    summary = {**review['summary'], 'domains': domains, 'chain_count_distribution': dict(chain_counts),
               'tasks_with_different_option_chains': different, 'failed_stages': failed,
               'native_translation_numeric_warnings': review['translation_warnings'],
               'new_attempts': budget['request_attempts'], 'estimated_ledger_usd': budget['estimated_ledger_usd'],
               'actual_charge_usd': None, 'reused': ['b001','pub013']}
    summary['tasks_with_readable_raw_chains'] = raw_chain_tasks
    summary['failure_details'] = core.read(HERE / 'failure_audit.json', [])
    summary['failure_reason_counts'] = dict(Counter(
        item.get('reason', item['status']) for item in summary['failure_details']))
    summary['accepted_verification_decision_changes_not_accuracy'] = dict(decision_changes)
    summary['representation_repair_files'] = [path.relative_to(HERE).as_posix()
        for path in sorted((HERE / 'run/tasks').glob('*/generation/round_*/representation_repair.json'))]
    summary['candidate_cap_cases'] = [{'task': row['task_slug'], 'audit': row['candidate_bound_audit']}
        for row in rows if (row.get('candidate_bound_audit') or {}).get('omitted_raw_indices')]
    tests = HERE / 'offline_tests.xml'
    if tests.exists():
        suites = ET.parse(tests).getroot().iter('testsuite')
        summary['offline_tests'] = dict(Counter({k: 0 for k in ('tests','failures','errors','skipped')}))
        for suite in suites:
            for key in summary['offline_tests']:
                summary['offline_tests'][key] += int(suite.get(key, '0'))
    core.dump(HERE / 'delivery_summary.json', summary)
    md = ['# 140 条解释材料交付报告', '',
      '这是原图上的静态提案—解释生成—核验材料，不是网页多步任务执行或防御有效率评测。', '',
      '## 实际完成状态', '',
      '- 固定任务：140；领域分布：' + domains_zh + '。',
      '- 生成完成：%s；核验结构校验完成：%s；现有文本的原生中文映射齐备：%s 条任务。最后一项不代表缺失的模型阶段已补全。' % (summary['generated'],summary['verified'],summary['translated']),
      '- 可阅览的原始解释链：%s 条任务（含结构校验未接受、但已返回可读草稿的任务）；不把这项等同于校验通过。' % raw_chain_tasks,
      '- 英文复用：b001、pub013 两条；新请求尝试：%s（上限 450）。' % budget['request_attempts'],
      '- APIYI 翻译请求：0；浏览器业务操作：0；GPU：未使用。',
      '- 规范化后多条解释指向不同选项：%s 条；规范化解释链数量分布：%s。未强行补写竞争链。' % (different, dict(chain_counts)),
      '- 已接受核验中的选择变化：保留原提案 %s，建议不同选项 %s，未给出推荐 %s。改变不等于纠错，没有使用 gold 给变化定性。' % (decision_changes['same_as_proposal'],decision_changes['different_from_proposal'],decision_changes['no_recommendation']),
      '- 新账本保守估算：$%.6f；这是估算，不是账户实际扣款。' % budget['estimated_ledger_usd'],
      '- 重试尝试：%s；HTTP 成功响应：%s；模型返回名称分布：%s。名称来自网关声明，不证明实际内部权重；HTTP 成功不等于内容校验成功。' % (accounting['retry_attempts'], accounting['http_success_count'], json.dumps(accounting['response_model_counts'], ensure_ascii=False)),
      '', '## 如何看', '',
      '直接打开 OBC140_TERRA_ZH_REVIEW.html，无需项目、服务器或网络。左侧筛选任务；点击原图放大；切换中文／英文；展开逐链核验、规则状态与原始 JSON。人工笔记可导出。', '',
      'O 是可见事实，B 是解释规则，C 是结论；这只是字段设计目标，不保证每条模型输出都遵守。单链、多链同选项和不同选项竞争在页面分别提醒。', '',
      '规则 active 不等于整链成立或行动被接受：还要查看 implication 与 recommendation。health010 的固定审查明确记录了规则保留、行动蕴含却被反驳且推荐为空的情况。', '',
      '英文模型记录保持原样。中文仅为独立阅览层，重复原文复用同一译文；译文不改正原回答。公开任务引用与图像引用分开标示，来源绑定不是内容真实性认证。', '',
      'run 中 translation=not_run 表示没有执行 API 翻译阶段；本轮原生中文侧车的完成状态在 review_data_zh.json 单独计算，两者不是同一个计数。', '',
      '沿用预先固定的格式处理：生成阶段只在 finish_reason=stop 时允许补末尾 JSON 闭合符；规范化候选最多按原生成顺序保留三条。原始响应及处理日志均保留，不是语义纠错；length 截断不补完。格式修补工件 %s 份（含复用来源如有），触发候选上限的任务 %s 条。' % (len(summary['representation_repair_files']), len(summary['candidate_cap_cases'])), '',
      '## 失败与证据限制', '',
      '失败阶段：' + (json.dumps(failed, ensure_ascii=False) if failed else '无结构性失败记录。'), '',
      '详细故障见 failure_audit.json。达到长度上限、引用路径格式不符、字面规则过滤与真正的视觉理解错误是不同事件。b011 的字面拒绝归因见 FAILURE_INTERPRETATION.md；其原始条件式解释保留，不提升为已核验规则。', '',
      '接口／输出失败原因分布：' + json.dumps(summary['failure_reason_counts'], ensure_ascii=False) + '。', '',
      'b001 的几何副链核验有“接近”被过强解释为“并非较小”的已知疑点，已保留提示。其他逐例疑点以 semantic_review.json / SEMANTIC_REVIEW.md 的实际审核范围为准；未审核不等于无问题。', '',
      '没有按隐藏答案修改输出，没有注入错误、强制答案或质量重采样。本材料不能证明解释都正确、错误提案恢复率，或长期规则保持能力。复用的两个开发例不算新的独立样本。', '',
      '## 费用口径', '',
      '运行限额使用全部输入×$2.5/百万＋输出×$12/百万的保守代理价，不扣缓存优惠。没有有效用量的尝试保留 $0.20 预留。此代理价不是供应商已确认的扣款上界。', '',
      '有 %s 次请求的用量别名出现零值／非零值等不一致。沿用既有规则取唯一非零值而不是累加别名；未解决的不同正值冲突 %s 项，用量规范化错误 %s 次。每个原字段与解析过程都留在 cost_summary.json，不把这项处理说成账单核实。' % (accounting['usage_conflict_attempt_count'], accounting['unresolved_usage_alias_conflicts'], accounting['usage_normalization_error_attempts']), '',
      '按返回用量及已归档公开标价的两种情景小计：' + json.dumps(accounting['known_usage_scenario_subtotals_usd'], ensure_ascii=False) + '；缺失费用尝试：' + str(accounting['cost_unavailable_count']) + '。', '',
      '第二情景仅假设缓存写入额外加价 25%，不是已核实的 APIYI 费率。详情见 cost_summary.json；旧复用请求费用不并入新账本。', '',
      '## 可追溯工件', '',
      '- PLAN.md / config.json：固定范围与配置。',
      '- run/runtime.json / runtime_source：执行源快照；run/tasks：完整请求、响应和英文记录。',
      '- translations/inbox / outbox：原生译文的逐字符串输入输出。',
      '- review_data_zh.json：双语阅览数据；run 中的原模型记录不受翻译影响。',
      '- PREDEPLOY_REVIEW.md：同家族独立上下文代码审查，不是跨模型确认。',
      '- offline_tests.xml / browser_check.json：工程检查，不代表研究假设成立。', '',
      '本轮离线回归计数：' + json.dumps(summary.get('offline_tests', {}), ensure_ascii=False) + '。', '',
      '本批处理结束后不自动追加任务或开发新机制。', '']
    (HERE / 'REPORT.md').write_text('\n'.join(md), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    summarize()
