"""Assemble offline Chinese translations and separate critical reading notes."""
import copy
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def main():
    notes = copy.deepcopy(read(HERE / 'EXPANSIONS_ZH.json'))
    candidates = read(HERE.parent / 'candidate_registration_20260926/CANDIDATES_ZH.json')
    notes['overview'] = [
        '实际状态：19 次请求尝试，14 次展开全部完成；4 个核验单元收到结果，第 5 个核验超时、结果未知，余下 3 个核验未发送。0 重试、0 付费 API、0 浏览器操作。固定程序已停止，不补跑。',
        '模型为已有本机 Qwen3.8-27B。18 份已返回响应的已知用量为 53,958 token；超时请求未返回用量，不能将其算作零，也不能把 53,958 当作完整总消耗。',
        '14 条都产生非空记录，C 都保持源候选的行动；这是候选表达结果，不是正确率或新增链数量。14 条都存入候选集合，10 条实际送入核验，其中 8 条有核验返回；另外 2 条的核验结果未知，4 条尚未送入核验。',
        '本页将原候选、旧展开、新 OBC 并排展示。蓝底中文由 Codex 离线翻译；阅览注释与原模型输出分开，不冒充用户人工确认。不能用这些固定开发例证明总体泛化或端到端纠错。',
    ]
    summaries = {
        'pub001_misleading': ['原误导图保持不变。上轮展开将登记版 TX 候选改成 ME；本轮保住 TX，但删减了原候选中相反的假设。保持结论不等于忠实保留依据。'],
        'pub001_normal': ['原正常图保持不变，底部原有 Clean／深色代表更高真实值的说明也保持；它是该图已有的明显方向线索，不是本轮新增，也不是盲化控制。'],
        'b002': ['关键案例：登记版反问原已提出“按物理柱高选择 Firefox”，旧展开却因未证实几何优先而拒绝；本轮成为非空 OBC 并进入核验。但柱高比较写在 B 而非 O，字段分工仍不完全忠实。'],
        'pub013': ['登记版 KS 的内在矛盾这次被记录，留给核验判定；IL 不再因额外全图唯一性要求被拒绝，但该路径原来已存在，不算新发现。读取覆盖版原本零候选，本轮不强造。'],
    }
    comments = {
        ('pub001_misleading', 'registration'): [
            ['C 不再被改成 ME。B 只保留“优先最低”而删掉原候选中相反的“优先最高”假设，因此不能说原矛盾全部忠实保留。', 'O 没有建立 TX 比 OK 更暗；即使接受最低优先，也尚不足以唯一推出 TX。'],
            ['沿浅黄 High 的图例读法得到 ME，核心读法保留。B 另添“线性”假设，不是比较高低所必需；这也不是新发现路径。'],
        ],
        ('pub001_misleading', 'coverage'): [
            ['B 新添“TX 与 OK 相等且 TX 是预定选择”的兜底，原候选没有此条件。不能为了保住 C 发明平局规则。此记录保留原样供阅览，不替模型修正。'],
            ['O 中的“表明数值明显更高”已经是解码结论，超出字面观察；核心图例读取路线仍可辨认。'],
        ],
        ('pub001_normal', 'registration'): [
            ['ME 的高端读法基本保留；本身是已覆盖路线。'],
            ['“优先最低风险”的解释被标成假设，而非公开业务事实；缺少 TX 比 OK 更低的完整比较。'],
        ],
        ('pub001_normal', 'coverage'): [
            ['新增了图底部已有的 Clean 文字说明，确实可见，不是隐藏信息；但这意味着展开并非只转写源候选。'],
            ['B 保留低风险优先为未核验假设，不可直接当作任务规定。'],
        ],
        ('b002', 'registration'): [
            ['保留比较印字 87、23、5 的 Edge 路径。'],
            ['这次不因读法优先级尚未证明就拒绝；C 保留 Firefox。', '关键“Firefox 柱子高于 Edge”却出现在 B，O 只列对象、印字和纵轴。不能由展示层替模型把该句挪进 O。'],
        ],
        ('b002', 'coverage'): [
            ['原候选的“Edge 柱最高”错读在新 O 中被省略；B 又保留“柱高比例并由印字确认”。C 相同不等于完整保留原读法。'],
            ['O 仍说 Firefox 第二高，图上它实际最高；B 将排除 Edge 的未声明政策作为假设保留。它是待排查候选，不是有公开依据的有效新路线。'],
        ],
        ('pub013', 'registration'): [
            ['没有发明反向指数来救 KS：B 承认浅色 High，却保留选深色 KS 的 C，让核验检查推导。', '新增 DE 深红色观察与原图不符；这不是应被认可的依据。'],
            ['保留 IL 浅黄对应 High 的条件链，不再强加必须全图唯一才可表达。旧初始链中已有类似路径，不计作反问新增。'],
        ],
    }
    verifications = {
        ('pub001_misleading', 'registration'): [
            '核验已返回。它指出旧链将 OK 看成橙色等观察错误；对新 TX 的 O 判支持、B 不确定、推导有效，仍未充分解决 TX/OK 比较及低风险优先依据问题。',
            '新 ME 的枚举写 inference=invalid，但 reason 自我修正后说推导有效，summary 也说有效。此矛盾原样保留，不改枚举、不把它算作自动核验成功。',
        ],
        ('pub001_normal', 'registration'): [
            '核验已返回。新 ME 为 O 支持、B 不确定、推导有效；新 TX 为 O 支持、B 被反驳、推导无效。',
            '它在同一任务中对最高风险优先说不确定，却以标准语义反驳最低优先；并把旧 O 未列 ME 当作反驳，推导时又补入 ME。核验状态不是人工真值。',
        ],
        ('b002', 'registration'): [
            '核验已返回。它认可新 Firefox 的 O，却以“任务规定使用标签”反驳 B，并判推导无效。公开任务实际只写使用 dashboard market_share values，没有明确规定印字一定胜过柱高。',
            '因此观察到的是这条条件路径已送入核验，不是它已被采纳；核验仍把读法适用性和条件推导混在一起。此处并不宣告 Firefox 应是最终正确行动。',
        ],
        ('pub013', 'registration'): [
            '核验已返回。新 KS 的 B 被反驳、推导无效，理由是“高端代表高风险”与选低端 KS 不一致；新 IL 的 O、B 与推导都获得支持。',
            '不过 KS 新 O 中 DE 的颜色错读仍被整组判支持，说明推导问题被发现不等于视觉核验全对。IL 的通过也不等于新增发现或已经业务提交。',
        ],
        ('pub001_misleading', 'coverage'): ['核验请求确已发送，第 19 次请求等待 120 秒后超时；无返回内容、无 usage，结果未知。不是被核验判错，也不能补用上轮核验。'],
        ('pub001_normal', 'coverage'): ['两个展开均完成；因前一请求超时后全局停止，本单元核验尚未发送。'],
        ('b002', 'coverage'): ['两个展开均完成；因前一请求超时后全局停止，本单元核验尚未发送。'],
        ('pub013', 'coverage'): ['上游零候选，无新展开；原计划仅核验旧链，但因全局停止，本单元核验尚未发送。'],
    }
    for case, case_notes in notes['cases'].items():
        case_notes['summary'] = summaries[case]
        for variant, unit in case_notes['variants'].items():
            unit['candidates'] = candidates['cases'][case]['variants'][variant].get('candidates', {})
            unit['verification'] = verifications[(case, variant)]
            for index, comment in enumerate(comments.get((case, variant), [])):
                unit['expansions'][str(index)]['comment'] = comment
    target = HERE / 'ANNOTATIONS_ZH.json'
    if target.exists():
        raise FileExistsError(target)
    target.write_text(json.dumps(notes, ensure_ascii=False, indent=2), encoding='utf-8')
    print(target)


if __name__ == '__main__':
    main()
