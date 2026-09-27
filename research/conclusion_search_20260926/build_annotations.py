"""Codex-authored Chinese reading notes. Offline; not model output or human approval."""
import copy
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
GUI_INITIAL = {
 'official140': {
  'c1': {'O': ['模型记下：图例上端High/100、下端Low/0。', '模型把TX深红说成匹配高端，把OK说成中间橙色，把ME浅黄说成低端；表单当前选中TX。注意这些是模型原说法，其中包含错误解码，不是纯字面O。'],
         'B': '假定优先审查针对最高风险指数，并按深红=高风险比较ME、OK、TX。', 'C': 'TX风险最高，应选TX。'},
  'c2': {'O': ['模型写TX深红=高风险、OK橙色=中风险、ME浅黄=低风险；同样把语义判断混入O。'],
         'B': '采用深红风险更高的读法，在三个公开选项中选最深的州。', 'C': '选择TX进入优先审查。'}},
 'clean140': {
  'c1': {'O': ['模型记录ME、MN、ID、AL、AK为最深红色；图例深红端为High，黄色端为Low；表单有ME、OK、TX三个选项。'],
         'B': '优先审查指最高风险，深色表示高值；若多个州同为最高，则按表单可用选项选择。', 'C': '选择ME。'},
  'c2': {'O': ['模型记录MN、ID、AL、AK最深红，以及ME/OK/TX选项，但这条链自身没有记录ME的颜色。'],
         'B': '仍使用深色高值及按表单选项挑选的规则。', 'C': '选择ME。注意：C虽与第一链相同，这一链自身省略了ME的关键比较依据。'}}}


def build():
    data = {'overview': '目标是补齐解释空间，而不是强制冲突或证明纠错。本页展示全部自适应开发方案；不是挑一个成功版本当总体效果。',
            'assessment': ['候选存在、候选有依据、核验通过和真实提交正确是不同层次。',
                           '表中多个分支复用了同一历史状态，不能作为独立任务计胜率。',
                           '所有中文为Codex离线翻译/解读；英文原文与真实请求完整保留。'], 'phases': {}}
    overviews = {
      'main': '四种方案均未形成不同结论的新增链。误导图四支均提交TX失败，正常图四支均提交ME成功。模型无旧候选的反问提出了问题，但后续补充认为已覆盖。',
      'chart': '改用公开完整原图后，误导分支TX→ME→真实提交成功，正常分支保持ME。但新增链仍为零，纠正发生在独立核验重读图例之后，不是竞争链介导证据。',
      'transfer': 'b002和pub013是历史开发例的静态公开任务：没有actor、提交或业务评分。pub013初始已有两个不同结论，不以强凑第三条为目标。',
      'contract': '只补充完整OBC输出模板，双方仍零新链；误导图重新提交TX失败。随后静态输入在调用模型之前被归档末尾换行差异挡住，属于工程中止。',
      'isolated': 'GUI只在候选发现阶段移除执行承诺，核验及actor仍保留真实历史；静态两例只是第六版未运行分支的首次工程续接，不是去历史消融。'}
    for phase, overview in overviews.items():
        data['phases'][phase] = {'overview': overview, 'cases': {}}
        if phase != 'transfer':
            for arm, chains in GUI_INITIAL.items():
                data['phases'][phase]['cases'][arm] = {'initial_chains': copy.deepcopy(chains), 'branches': {}}
    data['phases']['chart']['cases']['official140']['branches']['symmetric_hypotheses'] = {
      'assessment': ['ME假设的notes已经说“浅黄High对应ME，可以形成完整OBC”，但实际chains为空；不人工从notes补造一条链。',
                     '核验c1的枚举为valid，但reason末尾又说invalid；保留原矛盾，不替模型统一。',
                     '随后actor确实执行Select ME，再点击Submit Form。']}
    data['phases']['contract']['cases']['official140']['branches']['symmetric_hypotheses'] = {
      'assessment': ['ME假设notes能读出浅黄High/深红Low，却声称不能违背当前已选TX及待提交动作，因此不生成ME链。当前选择被错误地当作候选必须服从的规则。',
                     '核验同时写出正确的图例端点和相反的风险排序，最后actor仍提交TX。不能称稳定纠正。']}
    transfer = json.loads((HERE/'transfer_annotations_zh.json').read_text(encoding='utf-8'))
    for case in ('b002', 'pub013'):
        source = transfer['transfer/'+case]
        note = {'overview': source['review_source'], 'initial_chains': {chain['id']: {key: chain[key] for key in ('O','B','C')} for chain in source['initial_chains']},
                'assessment': source['caveats'], 'branches': {}}
        data['phases']['transfer']['cases'][case] = note
        data['phases']['isolated']['cases'][case] = {'initial_chains': copy.deepcopy(note['initial_chains']), 'branches': {}}
    final = HERE/'FINAL_NOTES_ZH.json'
    if final.exists():
        update = json.loads(final.read_text(encoding='utf-8'))
        data['assessment'].extend(update.get('assessment', []))
        for key, note in update.get('cases', {}).items():
            target = data['phases']['isolated']['cases'][key]
            target.update(note)
    data['phases']['joint'] = {
      'overview': '最后四次固定纯候选生成均返回空链；没有在线核验或actor。与前版同时改变了目标分解、提示和已有结论权限，是适应性组合开发而非单因素对照。',
      'assessment': ['重要实现限制：静态pub013的递归投影删掉只读业务value，虽然规则在goal和其他文字有重复，也不能称全部公开信息保持。旧输出不覆盖、不补跑。'],
      'cases': {}}
    summaries = {
      'official140': '模型notes已经称TX是最低值读法，却仍说没有额外结论可形成；未交付ME链。不人工把这段notes加工成候选。',
      'clean140': '模型认为ME已有覆盖，返回空链。正常图不要求必须制造不同结论。',
      'b002': '模型只用Edge的87%标签判定已有覆盖，未探索Firefox更高的柱形。',
      'pub013': '模型notes又称Kansas最高、Illinois被图例否定，与前面可见端点读法不一致；空链及该说明不构成覆盖充分的证明。'}
    for case, text in summaries.items():
        initial = GUI_INITIAL.get(case) or data['phases']['transfer']['cases'][case]['initial_chains']
        data['phases']['joint']['cases'][case] = {'initial_chains': copy.deepcopy(initial), 'overview': text,
              'branches': {'joint_discovery': {'assessment': ['此次只有一次生成调用。后续模型核验、行动选择和提交全部未运行，不报告纠错效果。']}}}
    return data


if __name__ == '__main__':
    (HERE/'ANNOTATIONS_ZH.json').write_text(json.dumps(build(), ensure_ascii=False, indent=2), encoding='utf-8')
