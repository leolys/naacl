# 新授权六配置全量比较：开跑前对抗审查

日期：2026-09-27。审查者为独立Codex subagent；本文件是代码与工件审查，不是人工语义认证，也不是模型效果结果。未调用模型/API/SSH，不运行资源启停或清理，不使用暂停中的ARIS，不修改程序、旧实验、原图或评分。

## 1. 本轮范围与旧实验边界

新授权允许plain/v3/v4/v5/v6/v7各fresh运行同140个指定单图任务。840是配置单元数，不是840独立任务，也不是140对正常/误导图。旧四版开发的数值/语义门槛未通过、无FREEZE的停止记录不改写为通过；本轮是另立的全量描述性比较。

协议明确保留旧275条O/B、原任务/原图/选项顺序/gold，不按本轮结果调提示或挑样本，分列原24开发与其余116、fresh v3与历史v3。候选生成历史成本不等于零；plain一调用与核验三阶段不等计算量。部分B内嵌行动语义，因此不称严格C盲审。

## 2. 已独立完成的固定资产与排程核对

使用本地只读脚本逐项核查，未执行prepare或runner：

- 140份input和140份原图的SHA与来源manifest相同；275条固定O/B对应原有候选。
- 六个提示文件逐字节与已封存来源相同；schema_v3与原v3相同，schema_new与上一轮固定schema相同。
- schedule精确等于事前round-robin生成规则；840个(unit, version)唯一且完全覆盖140×6。四worker各35任务、210配置，同一任务六配置均属于同一worker。
- 每一版本出现在六种组内顺序位置的次数为23或24，轮转不由结果驱动。
- 全140的在线contexts实际函数只投影goal/public_task/options；后续精确添加固定records、真实READ和真实reviews。未发现将离线答案、family或历史选择投进请求的代码通路。
- 正常主流程2240次调用，另4次控制；每worker上限650，四个worker及独立全程锁共同限制总上限2600。失败/重试记录为尝试，未知传输不自动补发。

v3接口差异不限于数组与对象：它沿用原自由字符串选项schema和原解析/校验逻辑，而新版有公开选项枚举、唯一choice/stop检查及重复JSON键检查。最终比较应继续将接口失败和语义效果分开，不能声称纯提示因果对照。

## 3. 资源安全审查及已落实修复

最初发现的资源问题是以40–43GB占用替代应用身份、允许低显存未知应用共卡，以及guard继承不确定CUDA映射。修订版已落实：

- 只向argv和start_ticks均匹配的容器guard PID发送SIGTERM，无宿主候选PID、未知作业或GPU7的信号路径，也无强杀。
- 宿主186000仅为待证候选；明确记录namespace映射未知。精确guard退出后要求候选消失，目标GPU0/2/3的applications为空；每个模型实际启动前再次检查apps为空、GPU UUID和空闲显存。
- guard显式设置PCI_BUS_ID及1/4/5/6 mask。verify-guard核对子进程身份、环境、完成分配日志和相较无guard快照新增的实际GPU集合；仅启动supervisor的记录明确不是readiness。
- 新副本启动比对原GPU7服务的真实PID/start_ticks/argv与配置，以及其配置环境；仅改指定端口/GPU和独立cache。

已读版本resource_manager.py SHA为`cd634468b2168520164545cfd02bc20278737257a8c09b710d2c8dbc32736f40`。在主执行者的新鲜检查和verify-guard实际通过、主机RAM足够的前提下，该资源代码没有剩余加载阻断。此处没有由审阅者独立SSH确认远端运行状态；主执行者报告的guard恢复和模型加载须由其真实工件支撑。权重加载放行不等于推理面板放行。

## 4. runner恢复与输出隔离

每worker独立账本/summary和全程非阻塞flock；每版本/任务/阶段独立路径。不可变请求、响应、accepted、result采用exclusive-create；只有自己持锁的summary/ledger允许原子更新。相同case的六版在同端点串行，不跨worker迁移。

最初指出的“响应已落盘、账本仍pending”的崩溃窗口已补reconcile_archived_responses：只从原响应离线恢复HTTP/model/usage，保存含原事件的sidecar，不新增请求；没有归档响应则永久阻断自动重发。strict bool控制检查也已修复，数字1不再被当作布尔true。

这两项修复是基础设施可靠性，不是视觉核验进步。当前审查读取了实现和测试源码，未自行调用线上模型；主执行者报告的mock测试数量应以其独立测试工件为准。

## 5. 最后开推理前待核对项

以下意见已经发给主执行者；在实际修复或明确防护落盘前，不将本文件当作整体验收通过：

1. **监听端点必须与身份记录的API PID绑定。** 当前dispatch分别检查PID/argv/env与端口health/models，尚未直接验证该端口监听socket属于同一PID。副本仍加载时若另一同名服务占端口，独立两项检查不足以证明它们为同一服务。可用ss或/proc socket归属进行只读检查。
2. **watchdog必须保护合法恢复客户端。** 仅等待首次launched PID集合退出，会漏掉重新启动的同worker客户端。建议在cleanup前非阻塞取得四worker全程锁，任一锁忙则继续等；持锁执行cleanup，避免中途恢复客户端仍请求时清理其模型。
3. **部分dispatch成功后也应留有子进程身份。** 建议每个Popen成功立即独立落盘，不等四个都成功；若后续启动失败，已启动客户端和收尾动作必须仍可追溯，不能因缺总launched文件成为无人跟踪的工作。

cleanup代码只遍历本轮前三个模型、核对PID/start_ticks/argv后SIGTERM；不碰现有GPU7。等待后只有applications为空且GPU UUID/内存符合的卡才恢复guard，不驱逐新占用者。恢复guard记录明确PID不是readiness，最终报告不能仅凭启动记录宣称恢复完成。

## 6. 封存与上传包边界

已完整阅读seal_and_bundle及unpack：包仅纳入指定运行源码、固定输入/图、config/manifest/schedule、协议与合成控制图，排除offline和旧runs；解包先检查全部路径、重复名、已有文件字节，再以exclusive-create写入，不覆盖不同内容。manifest包含family等运维/分析元数据，实际contexts不向模型投影；“未向模型提供评估信息”应以真实请求为准，而非仅凭包名public-only。

最终封存必须对应实际启动代码。审查中曾看到初版RUNTIME_SEAL/ONLINE_BUNDLE已生成，随后尝试校验时seal已不在原位置；主执行者正处理开跑前修复，故本文件**未认证最终ZIP/封存SHA或远端包内容**。应保留初版构建记录，在首次推理前重新生成一致的seal/包并独立核对，不据结果追改已运行版本。六提示、schema、schedule和固定输入不随基础设施修复变化。

## 7. 当前意见

固定资产、公平排程和公开投影检查通过；资源加载代码的此前阻断已修复。恢复账本与布尔控制的代码修复合理。最终推理仍等待第5节的实际防护及最终服务/封存证据，不预填效果或840完成状态。无论后续表现好坏，都应完整保留全部配置、失败、退化、空选项和成本，不逐任务拼最佳版本，不修改原评分。

## 8. 最终开跑前复核：代码阻断解除，运行前置条件保留

本节更新第5–7节当时的待处理状态，不覆盖初审记录。主执行者说明此前仍为零模型推理，并已将首版封存及待修dispatch/watchdog保存在`prelaunch_v1`。本次只读确认该目录保留dispatch.py、watchdog.py、首版RUNTIME_SEAL、ONLINE_BUNDLE与上传manifest；未改任何旧工件。

三项实际代码修复均已完整读取：

1. `dispatch.listener_owned_by`读取目标API进程的fd socket inode，并与其网络命名空间内`127.0.0.1:指定端口`、LISTEN状态的TCP inode对应，要求监听集合全部归该PID。它与PID/start_ticks/argv/env及health/models检查共同绑定端点，不再仅凭两个互不相连的检查。
2. dispatch每启动一个客户端就保存单独`launched_worker_*.json`；启动循环的finally保存当前已启动列表并为非空列表启动watchdog，后续Popen失败时已有进程仍有记录与收尾入口。
3. watchdog在初始PID均退出后，用ExitStack非阻塞取得四个worker锁；任一忙则释放已取得的锁并继续等待，全部取得后持锁执行cleanup。合法恢复的新客户端因此不会只因原PID退出而被清理服务器。

已读`checks/remote_offline_check.py`：它不安装包、不调用模型；核对seal/排程/140公开投影，使用自己创建的临时目录测试真实跨进程同worker锁拒绝、不同worker允许、释放后可用，并用自己创建的回环监听socket测试真实owner接受、错误owner拒绝。脚本使用的临时路径在本项目内，测试后由临时目录机制清理。**本审未在远端执行该脚本，也未在此时看到其真实结果文件，不能写成远端测试已通过。** 它是独立离线检查，不进入模型请求。

### 最终封存与ZIP实际核对

对新的canonical工件运行了本地只读检查：

- seal内306份文件逐SHA与当前源码/输入相等；ZIP实际307成员=这306份加RUNTIME_SEAL，无重复成员。
- ZIP CRC检查通过；307个成员解压字节全部等于本地对应文件；上传manifest的成员hash、ZIP hash、seal hash分别匹配。
- ZIP中不含offline、runs、workers、resources目录，也未纳入此次审查报告、旧实验结果或历史选择。
- 独立内存检查确认控制结果只接受`{"ready": true}`，拒绝`{"ready": 1}`、false及多余字段，不产生文件或模型请求。

|工件|核对后的SHA256|
|---|---|
|RUNTIME_SEAL.json|`17afcc2f2606d5783f57c6456fc82b375cc270e1dbadd68111e2637a3b333ab9`|
|ONLINE_BUNDLE.zip（15,338,643字节）|`16da751fb1636d25ecee70fb36286638d456770f2462ef202a17bb9060ebd2d6`|
|dispatch.py|`4f93dc5353e8dcf4a2adc6da41c6dd65a2df46c84192bfaf4fa75ee350fa1500`|
|watchdog.py|`b6c5395e2be7c4650662abd2800fa7ad5a4a6df5b180ceaa2d3303e9db26c204`|
|engine.py|`4700ee7aefcc90d7f444a7009036f08f83eb42ab6ee976e252717510160eba1b`|
|cleanup.py|`e3705d1d353a677fbcd076a2d4e4cf8715b70dfe9ff34db8b683361bf02c0aa6`|
|独立remote_offline_check.py（包外）|`8e63064219617154ddfd8d0411b9cd0bde0c05a7e794911ca07be6b62a41bc10`|

封存时间UTC 2026-09-27 06:52:20.165620。资源管理代码SHA仍为第3节已审版本；六提示、两schema及固定资产/排程仍由原来已核对的身份绑定。status.py只进行本地账本读取及health GET，没有推理请求；archive_prelaunch为已执行的开跑前可恢复归档辅助程序，不是结果导向重写入口，也不应在运行后再用来更改已封存源码。

### 当前最终意见

代码与本地封存层面**没有剩余开跑阻断**。可在远端离线检查真实通过、上传/解包身份一致、dispatch实际完成全部四个服务的PID/socket/环境/health检查后，按既定面板进入4次控制及固定模型请求。若任一前置失败，保留失败并停止对应启动，不能越过检查或更换未授权服务；无需因本审未亲自SSH而重复发模型请求。

这是前置工程审查，不认证模型表现、840单元完成或将来清理成功。特别是cleanup的恢复guard输出仍区分launch与readiness，最终资源状态需要真实核对；计费/尝试和接口差异仍按原协议完整保留。
