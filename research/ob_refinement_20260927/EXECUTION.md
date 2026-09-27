# 实际执行记录

## 推理前

2026-09-27 10:15：只读SSH核对已有API316818、Engine319282、guard282313，GPU7 UUID与原记录相同，health200、models含Qwen3.8-27B。没有启停服务或其他作业。远端项目AGENTS已读，不操作其ARIS安装；本地暂停要求保持。

在新目录执行`prepare.py`，机械复制旧公开输入与原图；140项、24开发/116应用，manifest SHA `1b84676b82c4cd4d43378c08dbbc5100409bbaf5860d0395110b51c1a1bb1f6f`。四条缺链采用上一轮已生成O/B，没有新SUPPLY调用。offline目录保存标签与旧对照，仅供本地分析，不上传运行包。

本地解释器为`D:/ths_Viswork/research/competing_rules_20260923/.venv/Scripts/python.exe`，设置PYTHONDONTWRITEBYTECODE=1、PYTHONIOENCODING=utf-8、PYTEST_DISABLE_PLUGIN_AUTOLOAD=1。

```text
python prepare.py
python -m pytest -q -p no:cacheprovider test_refinement.py --junitxml=offline_tests_001.xml
python -m pytest -q -p no:cacheprovider test_refinement.py --junitxml=offline_tests_002.xml
```

首次9通过3失败，原因是测试代码猜了png扩展名；改为从manifest读取实际图片名后12通过（0.64秒），未改原图或真实runner。旧失败XML保留。HTTP全部mock，没有真实调用。

对抗审查指出launcher父/子竞争同一非阻塞锁的竞态，首次推理前修复为父进程先释放预检查锁，worker再持有全程锁。返回PID不当作健康确认，之后仍须核对进程/状态。冻结判定细节也在任何新结果前补明确：每个对照分别跨至少2个家族净增、共同解析包含合法null、FREEZE绑定开发/基线汇总和定性审阅。

## 新一轮首个真实面板

`public_runtime_bundle_001.tgz` 15,313,930字节，SHA256 `dc3f6cef34765a322e6da53dd67fa10d712f6ae755c38d600874946d678db90b`，显式只打包公开data、manifest及运行源，不包含offline标签/历史选择。SCP至`/tmp/ob_refinement_public_001.tgz`，远端校验SHA及新目录不存在后解包。没有覆盖已有实验。

2026-09-27 10:36:21：远端新目录内运行：

```text
/mnt/data/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -B launch.py --version plain --panel dev
python -B status.py
```

客户端PID204707，日志`launches/20260927T023621_231227Z/stdout.log`。10:36:39确认进程存在、4次已发送尝试、3条completed。模型与GPU服务未启停。固定运行源码SHA保存在`runs/plain_dev/source_hashes.json`；之后仅开发独立离线评估/冻结工具和新提示版本，不改这份基础协议。

10:39:06 plain_dev完成。`collect.py --run plain_dev --terminal --output /tmp/ob_refinement_plain_dev_001.tgz`封存，下载后校验SHA `24916182ef383caf50c72f1a8334de59ec463669dc559c28f16fe37bd810c760`。取回SCP首次返回会话尚未完成，本地过早解包曾报文件未找到；待该同一SCP完成后解包成功，没有重发模型请求。

10:39:47启动`launch.py --version v4 --panel dev`，客户端PID214690，日志`launches/20260927T023947_786833Z/stdout.log`。10:51中期快照只包含前7条完整单元，保存在`partials/v4_dev_001`，不用来替代最终工件。

离线工具测试后续：`offline_tests_004.xml`14/14通过；评价发现不同域原生role字段不统一后，改用既有统一alignment_role并加全域枚举检查；`offline_tests_005.xml`21/21通过，包括六项冻结工件绑定mock。原标签未修改。实际plain请求由`integrity.py`及对抗审查分别核对，24张请求图字节与固定原图相同，原response/accepted/result一致。

展示页面仍在离线工程调试：初次本地Python对无encoding声明的长中文源文件报编码错误，显式UTF-8声明后生成。前两次页面QA保留了搜索子串和手机长文本溢出失败；这不涉及模型、数据或效果评分，待修复后另存新QA版本，不覆盖失败记录。

## v4终态与v5启动

v4于11:16:17完成。`collect.py --run v4_dev --terminal --output /tmp/ob_refinement_v4_dev_001.tgz`封存；完整包SHA256 `a8426663d0785e5e631474c5a858729e716a178bb09c6dd2bce823c1b67b630d`，8,287,030字节。420文件身份、72请求和原图字节由`integrity.py`核对；独立审查另查实际READ→VERIFY→DECIDE数据传递。三种对照的开发评价存于`analysis/v4_dev.json`，未满足冻结条件。

21项离线测试在`tests_008.xml`再次通过（0.49秒）；新增版本的无任务ID提示检查覆盖所有`prompts_*.py`，并非证明提示已泛化。实际开发HTML的24张图片、筛选、移动布局和离线无外请求检查记录在`qa_v4_dev_001/QA.json`，全部通过。

11:25:00仅上传新`prompts_v5.py`，核对远端SHA后运行：

```text
python -B launch.py --version v5 --panel dev
python -B status.py
```

客户端PID343044，日志`launches/20260927T032500_097111Z/stdout.log`。11:25:33实际进程、已保存READ及发出的VERIFY请求得到确认；全轮98次尝试。没有修改COMMON源码、重跑v4或发出116应用请求。子代理预审见`DEV_REVIEW.md`第10节。

11:30离线归档检查补齐实际前一阶段accepted→后续请求、原始响应→accepted→result→summary的一致性校验，仅改本地`integrity.py`，不改在线COMMON或模型输入。重新审计24+72请求均通过，结果另存`audit/plain_dev_integrity_002.json`与`audit/v4_dev_integrity_002.json`，旧审计保留。对抗审查新增`audit/v4_dev.json`覆盖全部24项、120个证据文件哈希；完整审阅不改变v4数值门槛失败的结论。

12:01:52 v5结束。12:03完整封存并下载`ob_refinement_v5_dev_001.tgz`（8,289,535字节，SHA256 `a999e4bcd995cdeff7ccef320e1e8481ba09295d4675b1606263d3ec8b181a45`）。对420文件及72实际请求、逐阶段实际输出传递核对通过。执行`evaluate.py --version v5 --panel dev --output analysis/v5_dev.json`得到17目标、4陷阱、2null、1other及numeric gate=true；语义审查另行拒绝pub008默认政策的依据，不制造FREEZE。`costs.py`核对全轮168份原始响应，623,457 tokens，无未知用量。三份运行中快照均仅包含当时已完成单元，保留在partials，不替代终态。

12:11:39：完成v5绑定审计与v6提示全文审查后，仅上传`prompts_v6.py`，远端核对SHA256 `5b324df3edc047dc32eb770cff963441820a6e27c252d44d7378e3f554b46c41`。运行`launch.py --version v6 --panel dev`，客户端PID17075，日志`launches/20260927T041139_153770Z/stdout.log`。预检health200，API/Engine/guard身份与前轮相同；12:17状态确认客户端实际发出请求，不把返回PID本身当成功。COMMON运行源码未改，没有上传offline标签，没有重跑旧版，也没有发出应用集请求。`tests_010.xml`记录21项离线回归通过（3.92秒），不是语义认证。

12:47:54 v6完成；`collect.py --run v6_dev --terminal --output /tmp/ob_refinement_v6_dev_001.tgz`封存8,294,046字节，SHA256 `ae886484995b39923e7d27af0361e8e730b0bb140bc7c06ac702608bf9b7405d`。下载到原先不存在的`runs/v6_dev`，执行`integrity.py`核对420文件及72真实请求、原图、前阶段输出和原响应；`evaluate.py --version v6 --panel dev --output analysis/v6_dev.json`显示12目标/7陷阱/2其他/3null，数值门槛false。`costs.py`核对全轮240份响应、910,494 tokens，无未知用量。

v7提示仍在首次调用前准备：READ/VERIFY逐字等于v4，DECIDE不同。`tests_012.xml`为21项离线测试通过（0.51秒）；之后只将尚未运行/尚未正式审查的v7 DECIDE草稿压缩到224词，未变职责或schema，当前提示SHA `afe52ec8d533d6f842bc1d91f88afd1ef7ca7119e960820572230deff149ac82`。最终审查针对该SHA，测试通过不能替代该语义审查。

v6终审绑定工件完成后，主审读取全部24旁注并执行`inspect_audit`：未见证据绑定问题，但numeric gate=false，未调用freeze。12:57:30确认远端无同名v7提示后仅上传该新文件，SHA一致，执行`launch.py --version v7 --panel dev`。客户端PID159810，日志`launches/20260927T045730_266319Z/stdout.log`；12:57:57确认真实进程及首次READ请求。当前健康/GPU/模型命令快照在`runs/v7_dev/preflight_*.json`，API316818、Engine319282、guard282313未变，无模型启停。`tests_013.xml`记录最终SHA的21回归通过。没有上传任何offline标签。

13:10与13:17分别保存v7的8项、12项完整中期快照，归档SHA为`13ad8c39cabdb69c7990173550ca8d7851cad1a9dd3dbf4f784bc9ffbe96f441`与`9a7e65c1f3e167e965492f955c73cd2619f4f2b15633ee02aba848fdb13d9855`，不含正在生成的单元，不替代终态。主审与子审分别核对首8个READ请求与v4完全相同、accepted文本均不同；追加离线compare_upstream.py用于终态全24核对，不进入在线运行器、不改变COMMON。

13:27第三快照18完整项，SHA256 `2522d64f843ce7ae86f47efe9b09a9cd1cb1908689d86a5a5ec348a7590dae33`，另存在partials/v7_dev_003。21项mock回归再次通过，tests_014.xml（0.54秒）。

13:36:43 v7自然完成，status确认客户端PID159810已结束，五个面板均finished，无application运行。13:38执行`collect.py --run v7_dev --terminal --output /tmp/ob_refinement_v7_dev_001.tgz`；下载前确认本地runs/v7_dev不存在，校验SHA `8876e75b610889939ccb1667041a0567ee9f3bfe6fd119404d547eb0cd064bf7`，8,289,509字节，再解包。summary SHA `5bdefa3bdda0819fc1ff010a645eaef6467c85df35eea0d16e7ef059c41b2fcc`。没有覆盖中期快照或旧轮结果。

```text
python -B integrity.py --snapshot ob_refinement_v7_dev_001.json --output audit/v7_dev_integrity.json
python -B costs.py --snapshot ob_refinement_v7_dev_001.json --output audit/v7_dev_costs.json
python -B evaluate.py --version v7 --panel dev --output analysis/v7_dev.json
python -B compare_upstream.py --output audit/v7_v4_upstream.json
python -B finalize_evidence.py
```

v7的420文件、72真实请求及实际阶段传递通过身份核对；评价15目标/4陷阱/1其他/4null，numeric_gate=false。最终聚合312响应与120配置单元、1860运行文件，并核对140份输入/图像及历史候选、原标签、历史summary/source身份未改。FINAL_COSTS为312请求、输入1,045,190、输出157,131、合计1,202,321tokens，无重试或未知用量。FINAL_INTEGRITY不认证语义正确；所有失败/退化版本保留。

finalize_evidence.py、compare_upstream.py仅在本地离线执行，未上传给在线模型runner，未增加模型请求。当前目录非Git工作树，因此没有伪造git diff；具体新增代码与快照身份可由本轮源文件和DELIVERY_FILE_MANIFEST核对。

13:44:31再次只读status确认客户端已ended、五面板finished、账本仍312，保存原输出至audit/remote_terminal_status.json。未启动后续应用或新推理任务，未停止已有Qwen服务/其他GPU作业。

v7全24对抗终审及主审逐项读取完成。主审发现pub009审阅把未在READ出现的4670/4560估值归给模型；审查者保留初稿audit/v7_dev_initial.json（SHA `50b86b3dfc862a6563c4fa728d9f451ecbbb85a7e62fecb57686dee1d49cb255`），正式audit只更正该旁注并在DEV_REVIEW第25节解释。正式audit/v7_dev.json SHA为`229bc068f618c2b969345f38c8229d6737108c0b36bc41755c7820e72ce2ee85`。所有输入/响应/结果和得分未变，主审只读inspect_audit仍返回pub008实际依据不足；没有执行freeze。该勘误不被写回模型输出。

13:53：生成最终24项中文展示并在已有Edge中离线检查：

```text
python -B build_review.py --version v7 --panel dev --output review_final_001
python -B qa_viewer.py --html review_final_001/OB_REFINEMENT_REVIEW.html --output qa_final_001
```

HTML为8,650,780字节，SHA256 `b6a47855e30a51031f70033a83b26102e4e82347f47944d69ec459bd8a2bfd89`。24图均能显示；新增相合2/损失2/状态未变20/失败0的筛选与分析一致；精确编号搜索、前后切换通过；桌面/手机/展开内容无横向溢出，0页面错误、0外部请求。主执行者实际查看desktop.png与mobile.png，中文、表格和状态说明可读。此为展示QA，不计作业务浏览器transition，不认证研究效果。

最终封包命令及旁置执行结果：

```text
python -B package_delivery.py --view review_final_001 --qa qa_final_001 --output OB_REFINEMENT_DEV24_DELIVERY_20260927.zip
```

该命令检查同一HTML的QA哈希、所需工件及敏感token样式，以不覆盖方式创建ZIP，再校验全部CRC和文件SHA；具体完成状态/文件数/大小/最终ZIP SHA以`OB_REFINEMENT_DEV24_DELIVERY_20260927.manifest.json`为准。包内DELIVERY_FILE_MANIFEST.json列逐文件身份，不重复打包原tgz及中期重复副本，不包含权重或凭据。
