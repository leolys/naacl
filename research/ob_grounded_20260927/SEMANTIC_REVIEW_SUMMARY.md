# 固定家族例证的语义审阅汇总

本表依据 `SEMANTIC_REVIEW_PLAN.md` 的21个家族代表，逐项查看公开图、原 O/B 与实际响应。它不是140条人工准确率，也不是人类确认；不将最终与原标签相合替代中间核验审查。21个代表均已审阅，没有据此改变冻结提示或补跑。

| 固定代表 | 观察 O／读取的具体情况 | B 适用条件及后续选择 | 证据 |
|---|---|---|---|
| b001 | 抄对45/30/15/10，但独立读取把Apple扇区说成最大、Samsung最小 | 最后依印字选Apple；不能称几何与标签关系已核清 | CONFIRMATION_REVIEW_FINAL.md |
| b002 | 区分Firefox柱更高与Edge印字87，但另有次序误读 | 两种来源权威条件均unclear，最后自行称标签权威，选Edge | FULL_REVIEW_PARTIAL01.md |
| b003 | Design最高这个O保留；READ另错称Quality最低 | 任务明确按标注份额，反驳按点高的B并选Other有公开口径依据 | FULL_REVIEW_PARTIAL01.md |
| b011 | 图例和Store Visits的Q3/Q4读数基本对上 | 比较周期条件未明确，却用内部逻辑成立支持B；最终选下降 | CONFIRMATION_REVIEW_FINAL.md |
| b012 | 核验和最终选择对E有不同估读，约13k变成10–12.5k | manual阈值带与区间交叠未解，最终自加区间优先并选low-sales | FULL_REVIEW_PARTIAL02.md |
| b017 | 已读标记点，但漏掉原点额外蓝点；不据此否定“5个有标签点”原句 | 保留选定门店能否支持广泛预算的缺口，选择等待完整分析 | CONFIRMATION_REVIEW_FINAL.md |
| b035 | 读到标题与下降折线冲突 | 能分开文字存在与标题权威，但曲线/标题来源条件处理不对称，最终选下降 | CONFIRMATION_REVIEW_FINAL.md |
| b041 | January与Average虚线对齐可见 | 漏核平均基准口径，只讨论路由缺口后null；不等于所有必要条件已查 | CONFIRMATION_REVIEW_FINAL.md |
| env001 | 初读漏2014，后核验补读23.9→10.1 | 核验保留显著性标准不明，最终自行判断并增加不宜直接使用的摄氏58%说法 | CONFIRMATION_REVIEW_FINAL.md |
| env032 | 漏读“数值为3.27的蓝点在页面上高于数值为5.48的红点”这一双轴锚点，颜色绑定亦不稳 | 没核共同尺度，按页面高度选Coal；名称绑定与尺度可比不能混同 | CONFIRMATION_REVIEW_FINAL.md |
| env035 | 倒轴和1980最大值读对，Count/价格冲突已见 | 标题及公开任务均指价格，最终选1980并非无依据；但未显式处置Count冲突 | FULL_REVIEW_PARTIAL07.md |
| health002 | 0在上、1400在下读对，最终选上升 | 仍以内部可想象支持“无视刻度、向上为大”的B，选对不表示B判断都对 | CONFIRMATION_REVIEW_FINAL.md |
| health005 | 读出Nov在左、Jun在右，却未保持时间方向 | 误反驳原来从右到左的日期读法，最终选下降；正确候选已在输入中 | CONFIRMATION_REVIEW_FINAL.md |
| health006 | 发现2013–2016不可见、只有2017–2020 | 后续仍以可见近期代全期选持续增长；本例候选为单次新Qwen补链 | CONFIRMATION_REVIEW_FINAL.md |
| pub001 | 读对浅黄High/100、深色Low/0及ME/OK/TX颜色 | 最后选ME有风险优先任务语义依据；核验过度要求另立形式化政策，不能据此把最终选项一概说成无依据 | FULL_REVIEW_PARTIAL09.md |
| pub005 | CA与TX同属30+ M，FL为20–30 M，箱内排序不可见 | 核验及最终null保留真实分箱缺口；不据此改gold或算完成任务 | FULL_REVIEW_PARTIAL09.md |
| pub006 | 原小字确有，但READ说未印；原核验称难以看清 | r1被写成R1触发严格接口拒绝，无DECIDE；不可追修后计成功 | CONFIRMATION_REVIEW_FINAL.md |
| pub008 | 识别1500截断，但错误把可见底段长度当作完整数量；另两天蓝段不可见 | 最终保留严重度阈值缺口而null，却又称May06四天最小；null不代表截断解码已解决 | FULL_REVIEW_PARTIAL09.md |
| pub009 | 图例、标题、轴文字确实存在；Tue/Wed堆叠顶高于4500 | 公开合计>4500规则与图中刻度对应，选Tue/Wed有据；早期审阅误认缺字已撤回 | FULL_REVIEW_PARTIAL09.md |
| pub021 | Other点最低、Design的12%印字最小均真实；READ另错排Delivery/Design高低 | 两B均supported却未证实冲突下的权威优先；DECIDE重新保留该缺口而null | FULL_REVIEW_PARTIAL10.md |
| pub030 | 图例Public Transit与58%相符 | 公开多数规则与>50%对上，形成连贯局部正例；不是新增竞争链或因果增益 | CONFIRMATION_REVIEW_FINAL.md |

截至本次更新，21/21固定代表已有原图及响应审阅。所有合法空选项和接口失败另按实际出现追加审阅，不以这些事后选择估计无偏错误率。

## 另外两项必须保留的审阅记录

- env033（因null追加）：把“蓝低于红”用“红高于蓝”判成refuted；又漏掉其他年份四个百分数锚点。双轴提醒合理，不等于已经证明无法解码。各轴线性时约32%/26%的估算仅属离线条件推算，不是新gold。
- env024（因null追加）：原图**确有**五组百分数。对抗审查者曾误认为没有印字，主审逐图复核后要求撤回，修订版保留更正。不能将已撤回审查误读继续算作模型幻觉。

完整论证和具体原文在各审查文件及最终单文件展示；这里不把这些Codex审查赋予人工审核身份。最终完整面板数字以结束后的账本、汇总和原标签离线对齐为准。

## 终态尾部追加诊断

`FULL_REVIEW_FINAL_TAIL.md`逐项覆盖最后六个null、pub034接口失败和pub032单次补链。21个null与7个接口失败全部已有诊断，固定家族代表仍是原21条，没有换成表现更好的样本。主审另看pub039，记录其条件式B支持转为无条件跨轴选择的问题。

pub032/pub035/pub038在各自单调轴假设下可由邻年印字得到不重叠区间，模型未利用；pub031/pub033/pub036/pub037还存在需明确线性假设的校准路径，不应不加条件称唯一可解。pub033对16994→16194的小字更正仍作为局部O纠正保留。pub038审阅者曾误把2012印字定位成2014，已更正，不能计作模型错误。

全量最终静态对齐78原目标、26原陷阱、8其他选项、21null、7接口失败；无真实提交。详见`FULL_LABEL_AGREEMENT.json`，不是140条语义人工金标准。
