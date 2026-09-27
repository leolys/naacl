"""Merge offline human-readable translations; never alters model records."""
import copy
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def main():
    candidates = read(HERE / 'CANDIDATES_ZH.json')
    chains = read(HERE / 'CHAINS_ZH.json')
    old = read(HERE.parent / 'proposal_completion_20260926/ANNOTATIONS_ZH.json')
    result = copy.deepcopy(candidates)
    result['overview'] = [
        '本轮按用户要求只开发反问模块的两种实现：候选登记版、候选登记加读取覆盖版；没有普通重看条件。',
        '关键进展：b002登记版确实由模型提出印字Edge与柱高Firefox两种读法，但后续展开器要求证明柱高应优先于印字，返回未展开。候选发现与完整链生成必须分开看。',
        'pub001误导图已正式登记并展开ME的图例读法；部分TX候选却依赖自行改为优先最低风险，不能算同一任务下可靠的另一种视觉解释。',
        '以下中文为离线翻译／审阅注释，不曾送入被测模型。原始错误和矛盾均保留，英文完整请求响应可展开。没有执行actor或业务提交。'
    ]
    for case, case_data in result['cases'].items():
        case_data['initial_chains'] = old['cases'][case]['initial_chains']
        for variant, unit in case_data['variants'].items():
            unit['new_chains'] = chains['cases'][case]['variants'][variant]['new_chains']
            actual = read(HERE / 'run_live_001' / variant / case / 'result.json')
            for index, expansion in enumerate(actual['expansions']):
                for chain in expansion.get('data', {}).get('chains', []):
                    key = 'expand_%02d/%s' % (index, chain['id'])
                    if key not in unit['new_chains']:
                        raise ValueError('Missing new chain translation: ' + variant + '/' + case + '/' + key)
    supplements = read(HERE / 'REVIEW_NOTES_ZH.json')
    for case, note in supplements['cases'].items():
        result['cases'][case]['summary'] = note.get('summary', [])
        for variant, vn in note['variants'].items():
            result['cases'][case]['variants'][variant].update(vn)
    target = HERE / 'ANNOTATIONS_ZH.json'
    if target.exists():
        raise FileExistsError('No annotation artifact overwrite')
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(target)


if __name__ == '__main__':
    main()
