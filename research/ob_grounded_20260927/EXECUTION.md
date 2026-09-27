# 实际执行记录（持续补充）

## 启动前

- 已读取AGENTS和旧真实请求/候选/核验，ARIS暂停保持。
- 02:16左右只读GPU/进程/health/models：服务GPU7 UUID未变、72259 MiB已用，API316818/engine319282；其他卡占用不触碰。
- 本地与远端各13项离线测试通过（mock不等于模型能力结果），本地JUnit为offline_tests_v1.xml。
- 公开输入包148单元（8开发＋140全量），SHA256 c4313e358a0f050b2ad390b1bea3b5305b0ecaa40d229c58b97c5b49344871e4，两端相同。远端仅新建ob_grounded_20260927；没有新建或覆盖旧runtime_aligned目录。
- 对抗审查见ADVERSARIAL_PLAN_REVIEW.md、CODE_REVIEW_V1.md。冻结绑定完整运行源及确认组不调参在首次调用前落实。

## v1开发

UTC 2026-09-26T18:29:36，使用现有环境：

```text
/mnt/data/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python /mnt/data/lys/CognitiveHijacking_CognitiveDenial/research/ob_grounded_20260927/launch.py --panel dev --version v1
```

仅测试进程PID207966（不是模型服务PID）。launches/20260926T182936_098199Z/stdout.log。与SSH断开解耦，PROCESS.lock阻止并发；560总尝试/UTC01:15截止。服务解码保持既有设置：BF16部署，thinking=false，temperature0.7/top_p0.8/top_k20/seed12345。

中途快照partial01仅供审查，非额外运行；下载SHA256 045902dddf007914bf4aeced1aa00aa35742549469c49653744a102b45f6dd9f核对。首个误导地图新选择ME，但仍把通常业务假设标支持；暂不宣称核验目标达到。

## 接续

heartbeat o-b 已建立，每20分钟、本轮截止09:15；只有本线程同任务接续。定时功能按OpenAI Docs核对：[官方说明](https://learn.chatgpt.com/docs/automations?surface=app)。这不保证电脑关闭后的本地接续；远端实验进程已独立启动并有自己的截止/锁/预算。不会借用新的API或作业资源。

## v1终态与v2准备

v1于UTC18:43:58结束：20请求、6完成、2个b002独立read空列表失败，无质量重试，88669token。终态包SHA256 f50f366996981177bf8346ddb1062ea35f61b8030285f55dadbedbd92783264c，与下载一致；解压到本地新runs/v1_dev。partial01/02与终态包分别保留，非多次运行。报告结构审计通过不等于语义正确。

v2增加一个B.reading_checked引用片段字段、独立read更字面化和严格三状态依据；原记录不删改。schema将原非空validator同步到生成约束，避免合法空数组导致跳过；这项为工程修复，不算视觉提升。run非对象HTTP JSON先归档，以及崩溃后usage旁证sidecar修复；均在v1终止/归档后修改。独立审查允许v2同8单元；本地15tests通过，JUnit offline_tests_v2.xml。

```text
python -m unittest test_grounded -q
python launch.py --panel dev --version v2
```

v1展示首版QA手机长链接横向溢出，不影响实验；修复仅viewer换行。保留qa_v1_dev失败QA并另建展示版，不改模型结果。

## v2 终态及 v3 测试

v2于UTC19:07:37结束：22次真实请求，7完成、1个coverage/pub013的read生成1500 token后截断，未进行其核验/选择。全局42尝试、193566 token；未因质量补跑。完整归档SHA256 6a48343d242f11807c6a2e931aa5bd9c8ce5704e035e039d2c92539fad4b93de，下载后相同。

v3本地 pytest 16 passed（offline_tests_v3.xml），远端同16项unittest OK；全为mock/静态隔离测试，不算真实能力结果。代码改动发生在v2进程退出后。原prompt_v1/v2及各runtime_source未重写。

## v3终态与冻结确认

v3于UTC19:33:03结束：24请求全部完成8单元，95734输入+18364输出=114098 token；与v1/v2合计66请求、307664 token，未质量重跑。终态archive SHA90062ec399a2d62803332749271ce4993f87aa955ac9b4a3e040b972a833f717，下载核对一致。

本地执行 `freeze.py --version v3 --review DEVELOPMENT_DECISION.md`，冻结时刻UTC19:37:36.571688。freeze额外核对当前源与实际开发快照一致且runtime_preserved，未放宽模型/输入限制。随后上传FREEZE及决定，远端 `launch.py --panel confirm --version v3` 启动PID400641（仅诊断客户端），日志launches/20260926T193756_699165Z/stdout.log。后续禁止修改五份绑定源或用确认结果调参。

另有3个离线标签对齐mock通过（offline_alignment_tests.xml），只验证精确公开选项匹配、重排/重复标签拒绝；不是任务评分验证。真实原标签导出在冻结之后调用原action_options，不调用score_submission或业务提交，记录原任务/模块哈希，隔离保存ORIGINAL_LABEL_ALIGNMENT.json。

## 确认终态与全140应用

确认于UTC19:55:40结束：36请求，135563 token，11完成（含1个null）及1个核验编号格式失败。pub006请求id=r1、响应R1，不能称为漏写候选，未执行DECIDE。终态包SHA10ee0de335e8e3742e5c9614809719ddd0a2f380cbd6e1289c7a7db3d563805b。12个结果不据质量补跑，同一冻结五文件继续使用。

全量启动前再次只读检查模型/guard身份及GPU，未改变任何作业。UTC20:01:43远端执行：

```text
env PYTHONDONTWRITEBYTECODE=1 /mnt/data/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python /mnt/data/lys/CognitiveHijacking_CognitiveDenial/research/ob_grounded_20260927/launch.py --panel full --version v3
```

仅诊断客户端PID9769，日志`launches/20260926T200143_341127Z/stdout.log`。全量140包括复用全部12确认终态，不重复请求；不是全量140再加12个独立样本。全量结束前不修改冻结五文件，不自动补跑失败。

本地离线命令（不调用模型）：

```text
python audit_runs.py --runs v1_dev v2_dev v3_dev v3_confirm --output ACCOUNTING_THROUGH_CONFIRM.json
python score_choices_offline.py --run v3_confirm --alignment ORIGINAL_LABEL_ALIGNMENT_v2.json --output CONFIRM_LABEL_AGREEMENT.json
python report.py --run v3_confirm --output review_confirm_001 --agreement CONFIRM_LABEL_AGREEMENT.json
python qa_viewer.py --html review_confirm_001/OB_GROUNDED_REVIEW.html --output qa_confirm_002
python -m pytest -q -p no:cacheprovider test_offline_alignment.py test_offline_scoring.py --junitxml=offline_report_tests_v2.xml
```

7项离线helper测试通过；确认HTML的12图、筛选器、锚点、移动端及展开证据无横向溢出，0远端网页请求。这是展示QA，不计作benchmark浏览器操作，不证明核验准确。旧版译文混旁注问题经审查后使用新`NEW_EVIDENCE_ZH_v2.json`分块展示，旧派生文件保留、原模型输出不变。

读取服务部署配置保存`service_snapshot/`。其中`deployment_status.json`时间仍是原2026-09-26 11:10:48（历史快照，不改为本次检查）；当前服务身份以各run的preflight文件为准。配置/依赖记录没有启动新服务。

## 全量运行期间的只读收集与离线改动

PID9769继续运行；未改冻结五文件。UTC21:09:19的partial04含完整商业47条加复用env001，仍为running。归档SHA `78c648511d8908bfb0db69c59a1413d0d3fcc411c49d0e9a701b603d7f563820`，12,872,514字节，下载后相同。命令模式为：

```text
ssh hexin_2007_K_root "env PYTHONDONTWRITEBYTECODE=1 /mnt/data/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python /mnt/data/lys/CognitiveHijacking_CognitiveDenial/research/ob_grounded_20260927/collect.py --run v3_full --output /tmp/ob_grounded_v3_full_partial04.tgz"
scp hexin_2007_K_root:/tmp/ob_grounded_v3_full_partial04.tgz hexin_2007_K_root:/tmp/ob_grounded_v3_full_partial04.json D:/ths_Viswork/research/ob_grounded_20260927/
tar -xzf ob_grounded_v3_full_partial04.tgz -C full_partial04
```

partial01–04是同一个run的累积快照，不是重跑；终态之前不解压到canonical `runs/v3_full`。

```text
python -B -m pytest -q -p no:cacheprovider --junitxml=offline_regression_before_full_final.xml
python -B check_snapshot_links.py --snapshots ob_grounded_v1_dev_partial01.json ob_grounded_v1_dev_partial02.json ob_grounded_v2_dev_partial01.json ob_grounded_v2_dev_partial02.json ob_grounded_v3_dev_partial01.json ob_grounded_v3_confirm_partial01.json --output SNAPSHOT_LINK_AUDIT_THROUGH_CONFIRM_v2.json
python -B report.py --run v3_confirm --output review_confirm_005 --agreement CONFIRM_LABEL_AGREEMENT_v2.json
python -B qa_viewer.py --html review_confirm_005/OB_GROUNDED_REVIEW.html --output qa_confirm_006
```

以上使用本地 `research/competing_rules_20260923/.venv/Scripts/python.exe`，无推理调用。26项现有离线回归通过；6份早期metadata的423个不可变文件引用相同；确认展示有11/11最终理由中文摘要，12图及筛选/手机展开检查通过。主审目视手机展开图；最后另作表头首列宽度调整，最终全量仍需独立渲染QA。

中文摘要通过实际英文全文键匹配，未改原输出；截至本记录已包含商业45条DECIDE（b019/b047无DECIDE）及全部确认DECIDE。旁注与译文分开。冻结英文提示的中文对照在PROMPTS_ZH.md。任何结构/展示通过都不是语义核验通过。

## partial05 与离线中文补充

UTC21:22:41使用相同collect/scp/tar流程收集 `ob_grounded_v3_full_partial05.tgz/json`，16,467,753字节，SHA `981127ed7c75bffe2fb81cf33a4dd9ad976b7c003dbcd861caa6cc6d95bc2c73`，解压至新 `full_partial05`。58终态，未替换canonical目录，未重新推理。收集后ps仍确认PID9769存活。

```text
python -B -m pytest -q -p no:cacheprovider --junitxml=offline_regression_partial05.xml
```

26项通过。中文缓存新增10个环境任务的最终理由和19条代表B核验理由；通过实际英文精确键关联，摘要与审查旁注不混写。`WORKED_EXAMPLES.md` 是对已归档结果的中文解读，不是额外模型输出或新人工标签。

## partial06/07 与双重视觉复核

沿用同一收集命令，`--output`分别替换为`/tmp/ob_grounded_v3_full_partial06.tgz`和`/tmp/ob_grounded_v3_full_partial07.tgz`；下载每份同名`.json`，核对SHA后解压至新`full_partial06`、`full_partial07`，不覆盖canonical。partial06：20,069,111字节，SHA `23d456dae400406b0004dcc73431daa5636d6e397cbf5f1a24d582aa180e3400`；partial07：21,491,572字节，SHA `31adc01ee82a06c3076bc6f72126cd4ceb09d2e4e494c0382bba5ea44c60fc74`。它们是累积快照，不累加成本。

```text
python -B report.py --run v3_confirm --output review_confirm_006 --agreement CONFIRM_LABEL_AGREEMENT_v2.json
python -B qa_viewer.py --html review_confirm_006/OB_GROUNDED_REVIEW.html --output qa_confirm_007
```

本地中文摘要已扩至248个英文精确键，含所有已完成商业/环境B理由和最终理由。确认展示20/20已接受B理由和11/11 DECIDE理由有中文摘要，原英文均保留；0远端网页请求。READ和O证据没有宣称已全译。两处旧中文摘要精度修正仅作用于派生缓存：b013保留≥5,200且严格<20,000，b022注明Region可比是模型的解释，不当已确证事实。旧HTML不改写。

主审与对抗分别查看env024原图并确认五组印字实际存在，撤回审查者初稿的缺印字指控；也分别复核env033其他年份四个数字锚点及O同义关系误反驳。审查文档保留更正，不改模型响应、gold或冻结提示。env035正确倒轴解码与指标冲突分层记录。具体见FULL_REVIEW_PARTIAL06/07.md。

## partial08/09 与中文候选对照

沿用collect/scp/tar命令分别收集`/tmp/ob_grounded_v3_full_partial08.tgz`和`...partial09.tgz`。partial08为22,686,185字节，SHA `43015996e7401d484f025998bd735f26460926d037ac854d14d7fbddeb76a1fd`；partial09为30,022,923字节，SHA `d6dcf33e1c55f1e5dcddb9ade28981ae7c6b9d2a867265f1f56462c2cc9baa21`。分别解压新目录，均无收集期间文件变化，没有替换运行结果。

```text
python -B -m pytest -q -p no:cacheprovider --junitxml=offline_regression_partial08.xml
python -B report.py --run v3_confirm --output review_confirm_007 --agreement CONFIRM_LABEL_AGREEMENT_v2.json
```

26项回归通过。新增`SUPPLIED_CANDIDATES_ZH.json`仅离线翻译本轮单次Qwen补链O/B；先含b013/b033/health006的39句，pub032必须等待真实生成。`NEW_EVIDENCE_ZH_v2.json`扩展B/DECIDE及固定例证O理由中文。没有API翻译，原错误如“Q2/Q6相邻”“2015最低”照原文保留，评价另写旁注。新展示的最终QA仍待完整full。

pub009原图和实际请求图SHA均为`0de5e97211bfc1c8498144624da54c89b2a5eca56b21c0410572e0993989435e`。主审和对抗撤回初次预览的缺字质疑，重新原分辨率确认所有标题/图例文字存在；误读成因未确定，不改模型结果。应保留模型真实的小偏差（1000最低刻度与更低边界不等价），而不能将审阅错误当模型幻觉。

## partial10 与固定家族审阅完成

同一collect命令收集`/tmp/ob_grounded_v3_full_partial10.tgz`，下载同名json，核对SHA为`a40a004309e0b056f518c0d6b77cba7500875b3bddd8d98ac39d3ed5d6d9152f`，38,846,624字节，解压至新full_partial10。122终态不是最终全量；pub021新增null及pub015/pub019新增接口失败均保留。

```text
python -m pytest -q test_grounded.py test_artifact_audit.py test_offline_alignment.py test_offline_scoring.py --junitxml=offline_regression_partial10.xml
```

26项通过，15.08秒。21家族代表全部完成双重离线审阅，不是人类金标准。中文理由精确源键已468条。pub019原图caption的提示性内容另据实际图和原资产SHA披露，未改输入。输出最终全量分数、成本和完整展示仍须等待同一运行的终态。

## 最终归档、离线审计与展示

全量同一客户端在北京时间07:12:40结束。沿用collect的`--terminal`模式收集`/tmp/ob_grounded_v3_full_final.tgz`及同名json，下载后SHA核对一致：`4a28c560d81a67b24be98ac83673ddcde8f66156046de807601edd1da63837d8`，43,761,374字节。第一次解压到canonical `runs/v3_full`，没有覆盖旧partial或确认结果；采集时没有变化的文件。

本地离线命令使用`D:/ths_Viswork/research/competing_rules_20260923/.venv/Scripts/python.exe`，设置`PYTHONDONTWRITEBYTECODE=1`、`PYTHONIOENCODING=utf-8`；pytest另设`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`：

```text
python finalize_costs.py --snapshot ob_grounded_v3_full_final.json --output FINAL_COSTS.json
python audit_runs.py --runs v1_dev v2_dev v3_dev v3_confirm v3_full --output FINAL_ACCOUNTING.json
python audit_final_artifacts.py --ledger FINAL_COSTS.json --output FINAL_ARTIFACT_AUDIT.json
python check_snapshot_links.py --output SNAPSHOT_LINK_AUDIT.json
python score_choices_offline.py --run v3_full --alignment ORIGINAL_LABEL_ALIGNMENT_v2.json --output FULL_LABEL_AGREEMENT.json
python report.py --run v3_full --output review_full_001 --agreement FULL_LABEL_AGREEMENT.json
python qa_viewer.py --html review_full_001/OB_GROUNDED_REVIEW.html --output qa_full_001
python -m pytest -q -p no:cacheprovider test_grounded.py test_artifact_audit.py test_offline_alignment.py test_offline_scoring.py --junitxml=offline_regression_final.xml
```

全部命令退出0。483次真实请求逐一对账，473份accepted内容与原响应一致，17份快照12,458文件引用一致。最终离线26测试通过（3.11秒）；展示140图解码、锚点、筛选、桌面/窄屏/展开检查通过，无HTTP请求或脚本错误。主审查看desktop/sample/mobile_evidence截图确认文字与证据布局可读。QA绑定HTML SHA256 `6bc3fbe8dfeb981328b80fe5db3f8a79e8bc3316749da6865c820f424e61ec1f`；单文件42,026,510字节。

此阶段只有离线中文整理（133/133最终理由、266/266 B理由、126/745 O依据）、报告和展示，不新增推理。完整英文和失败均保留，自动审计不等于语义正确。

07:28只读远端检查：已有Qwen/API/占卡进程仍在，实验客户端9769已退出，健康接口200；最初ps的`--ww`参数错误随后改成`-ww`成功，不把失败检查称作确认。详细实录见`service_snapshot/closeout_readonly_20260927.md`。本轮只暂停临时heartbeat o-b，不停模型或占卡。

## 对抗终审后的最终展示002

按终审仅调整中文“未建立”与“提示”两处语气，不改在线提示、模型英语、结果或原图。旧001保留，执行新的离线命令：

```text
python report.py --run v3_full --output review_full_002 --agreement FULL_LABEL_AGREEMENT.json
python qa_viewer.py --html review_full_002/OB_GROUNDED_REVIEW.html --output qa_full_002
```

退出0，QA再次通过，002为最终入口。42,026,531字节，SHA256 `1f97bfec817543311cca4a806d99941f79de622cd5de232eae4957b539a0dc3e`；140图、0外部请求/错误、筛选/锚点/窄屏展开正常，主审再看最终桌面截图。全部真实请求仍483，没有翻译API。

最终打包命令采用以下参数；其实际执行结果以同名外部manifest为准，内部DELIVERY_FILE_MANIFEST列每个文件的字节身份：

```text
python package_delivery.py --view review_full_002 --qa qa_full_002 --output OB_GROUNDED_140_DELIVERY_20260927.zip
```

此段在打包前保存以一并进入包，不能仅凭列出命令就认为打包已成功。脚本不覆盖旧包，实际完成时须另外核对退出状态和manifest中CRC及逐文件SHA结果。

### 打包误报修复（仅离线）

首次打包在扫描`ZH_EXACT_CACHE.json`时退出1，尚未创建ZIP。检查三个匹配位置确认均为普通英文`task-…`词内的`sk-…`片段，不是凭据；未输出疑似密钥明文。将凭据前缀限定为非字母/数字/下划线边界，保留真实JSON键值与Bearer头的检测，未删减源材料或绕过整份文件检查。新增三个离线反例测试，不改冻结五文件、输入或模型输出。

```text
python -m pytest -q -p no:cacheprovider test_grounded.py test_artifact_audit.py test_offline_alignment.py test_offline_scoring.py test_package_delivery.py --junitxml=offline_regression_delivery.xml
```

29 passed，2.78秒，退出0。再次打包仍采用上一节相同命令和新文件名；第一次未生成ZIP，因此没有删除、覆盖或替换旧归档。
