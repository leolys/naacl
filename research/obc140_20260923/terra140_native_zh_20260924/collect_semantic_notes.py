"""Aggregate bounded, existing review artifacts without modifying model output."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXED = ('b002', 'b010', 'env001', 'env015', 'health001', 'health010', 'pub001', 'pub020')


def collect():
    flags, reports, missing = {}, [], []
    for slug in FIXED:
        report = HERE / ('semantic_review_' + slug + '.md')
        note = HERE / (slug + '_flags.json')
        if not report.is_file() or not note.is_file():
            missing.append(slug)
            continue
        value = json.loads(note.read_text(encoding='utf-8'))
        if set(value) != {slug} or not isinstance(value[slug], list):
            raise ValueError('Unexpected review flag structure: ' + str(note))
        if not all(isinstance(text, str) for text in value[slug]):
            raise ValueError('Non-text review flag: ' + str(note))
        flags[slug] = value[slug]
        reports.append((slug, report.read_text(encoding='utf-8')))
    (HERE / 'semantic_review.json').write_text(json.dumps(flags, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    lines = ['# 固定小面板语义审阅汇总', '',
        '本文件只汇总已存在的独立上下文 Codex 审阅工件。它不调用被测模型，不修改原模型英文、中文侧车、原图、任务或 gold。', '',
        '审阅范围固定为八条，覆盖四个领域；选择时 b002 已看过，其余七条尚未生成。不是随机总体质量估计，不替代数据所有者的人工确认。审阅为同家族／暂定意见，不宣称跨模型盲审。', '',
        '已有审阅报告：%s/8；尚无完整审阅工件：%s。' % (len(reports), '、'.join(missing) if missing else '无'), '',
        '| 任务 | 审阅工件 | 单独提示数 |', '|---|---|---|']
    for slug in FIXED:
        lines.append('| %s | %s | %s |' % (slug,
            '[查看完整意见](semantic_review_%s.md)' % slug if slug in flags else '尚未形成报告',
            len(flags[slug]) if slug in flags else '不适用'))
    lines.extend(['', '提示数为零只表示这次有限抽查没有留下独立提示，不是正确性认证。失败的固定样本不替换；未接受的核验原文不是正式核验结果。', '',
        '另外：b001 的既有几何副链疑点由旧验证继承，不算新发现；b011 是运行中追加的接口故障归因，见 [FAILURE_INTERPRETATION.md](FAILURE_INTERPRETATION.md)，不冒充固定八条之一。', '',
        '审查中发现的读图、蕴含和政策充分性问题只能按相应公开证据讨论。不能据此覆盖原标签或重写既有人工审核。', ''])
    lines.extend(['缺少显式数值阈值不自动证明任务无效，也不排除基于领域常识作判断；相关提示用于区分直接观察、判断假设与模型实际接受的结论，不为数据集重新裁定答案。', ''])
    for slug, body in reports:
        lines.extend(['---', '', '## 原始审阅全文：' + slug, '', body, ''])
    (HERE / 'SEMANTIC_REVIEW.md').write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps({'reviewed_fixed_cases': list(flags), 'pending_reviews': missing,
                      'new_model_requests': 0}, ensure_ascii=False))


if __name__ == '__main__':
    collect()
