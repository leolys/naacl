"""Offline Chinese reading notes; never supplements a model proposal or chain."""
import copy
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
old=json.loads((HERE.parent/'conclusion_search_20260926/ANNOTATIONS_ZH.json').read_text(encoding='utf-8'))
data={
 'overview':'本轮用全新短提示测试“先保留提案，再展开OBC”。真实结果：四例均返回零提案，展开器一次也没有运行；只有提案生成和对旧链的核验。不能把工程链路通过当成补链成功，也不能据此判断展开器能够或不能保留非空提案。',
 'assessment':['实际8次请求：4次提案、4次核验；0次展开、0次浏览器操作、0次提交、0次付费API。',
               'pub001误导图notes已得到ME的候选方向，却没有写进proposals。此处是提案交付遗漏，不是展开阶段拒绝。',
               '静态pub013四项readonly业务value完整保留；这次没有沿用上一轮误删value的投影。',
               '本轮同时改变短提示和阶段接口，没有同轮旧版控制组；不归因于单句提示，也不宣称任务恢复。'],
 'cases':{}
}
notes={
 'pub001_misleading':{
  'overview':'最重要的观察：模型在notes中写出ME浅黄对应High、TX/OK深红对应Low，并称ME是最合理的优先审查选择；但实际proposals=[]。输入的已有行动标签只有TX，所以ME本可成为不同的候选方向。未由Codex把notes改成提案或链。',
  'assessment':['提案notes中文：ME约90–100、TX/OK约0–20；虽然任务没明文写“选择最高”，通常风险优先审查针对最严重风险，因此ME最合理；模型随后称看不到其他读法，并返回零提案。',
    '核验本次识别了反向色标及OK颜色误读，否定旧TX链；但它把未提供的历史“当前选TX”控件观察当成已反证。该控件其实不在当前图输入中，不能以不可见直接判它历史上不存在。',
    '核验仍混合了事实适用性与条件推导：实际图与B不符，不自动等于“假定原O/B时C不成立”。没有执行actor，不能称TX已改成ME。']},
 'pub001_normal':{
  'overview':'模型认为ME已有依据、没有其他结论，返回零提案。正常图不要求一定新增；但这也没有让展开器得到真实非空输入。',
  'assessment':['提案notes中文：ME深红、OK/TX浅黄，ME风险最高，已有选择受支持；没有另外的读法。',
    '旧链核验仍把MN/ID/AL/AK等说成同为最深色；最终ME结论合理不代表所有O都正确。',
    '核验第二条链时承认该链O没有ME，却借第一条链/图的事实判其推导valid。候选是否自包含仍有问题。']},
 'b002':{
  'overview':'仍然漏掉柱高这条可见读取路径。模型只列印字Edge 87%、Firefox 23%，声称图面无歧义，没有形成提案。',
  'assessment':['提案notes中文：五类都有明确百分比，Edge 87%最大；模型说从柱宽、颜色或顺序也看不到反对印字的读法。它没有记录Firefox柱顶高于Edge这一高度关系。',
    '核验只确认了旧Edge印字链；确认已有链不等于检查解释空间是否完整。',
    '“印字→Edge／共同坐标下柱高→Firefox”是离线审查指出的候选路径，不是本轮模型生成。']},
 'pub013':{
  'overview':'原初始集合已经含Kansas和Illinois两种C，因此不要求强凑第三条。此次零提案的说明却把可选州都说成低值/中值，漏掉浅黄的Illinois。',
  'assessment':['提案notes中文：High对应浅黄100，但模型声称可选的IL/KS/DE均为低值或中值，最高的Oregon/Texas不在选项，所以没有有效提案。该说明包含对IL的图面误读。',
    '独立核验随后又正确指出IL浅黄High、KS深红Low，拒绝KS的反向风险解释并支持IL；这是阶段之间的读图不一致，不是已经展开了IL新链。',
    '旧KS链O里还有DE颜色误读，核验却整体标O支持；否定B后直接判条件推导invalid，也没有严格分开两种判断。']}
}
for case,note in notes.items():
    phase,source=('main','official140') if case=='pub001_misleading' else ('main','clean140') if case=='pub001_normal' else ('transfer',case)
    note['initial_chains']=copy.deepcopy(old['phases'][phase]['cases'][source]['initial_chains'])
    data['cases'][case]=note
(HERE/'ANNOTATIONS_ZH.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
