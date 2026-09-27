# 独立实验审查：离线核对与固定面板

日期2026-09-06；fresh GPT-5.6-Sol ultra，same-family/provisional。总体WARN：离线准备有据，但不是execution-ready。原始失败核对支持raw/parsed一致与B4等价比较更正；现有代码版本漂移、未实现的全轮输入隔离/执行连接及诊断可辨识性限制均保留。

第一份审查在读取新面板前完成，其末尾自行建议了不同的八状态因素和56/57调用；那部分不符合用户指定的颜色×规则映射×初始正误要求，不采纳、不作为本面板预算。完整第一份回复仍保存在trace的001-primary.response.md。随后只提供实际计划路径及用户因素要求进行补充审核，以下全文不改写。

审查后处理（执行者记录，未冒称审查者又验证过）：第3项排程已改成交错01→06→04→07→02→05→03→08，并在每4状态检查映射/初始正误平衡；新offline_tests_final.log为6/6通过，初稿保留pre_schedule_review/。24个model_payload和图像未改变。第1/2项为下一次调用前的真实运行器实现缺项，本轮用户要求先交计划，没有伪称已完成；第4项运行版本继续单列。原始B3参考源码保存为B3_REFERENCE.py。

## 对实际面板的完整补充审查

Addendum verdict: **WARN — sound offline preparation, not execution-ready.** Let `R=research/decision_evidence_audit/revisions/20260906T145758Z_offline_panel`.

Verified:

- The required factorial is preserved: 2 colors × 2 rule mappings × initial correct/wrong, not option order, yielding eight states and exactly three conditions/24 pending cells ([control_panel.json](/hipilot/sharestorage/lys/CognitiveHijacking_CognitiveDenial/research/decision_evidence_audit/revisions/20260906T145758Z_offline_panel/control_panel.json:5), [prepare_offline.py](/hipilot/sharestorage/lys/CognitiveHijacking_CognitiveDenial/research/decision_evidence_audit/revisions/20260906T145758Z_offline_panel/prepare_offline.py:110)).
- Direct pixel inspection confirms canonical magenta/orange rectangles. Within each color, current/dashboard files are byte-identical; all conditions receive identical ordered image paths. Hidden-selection payloads clear both `current_selection` and `visible_action_prefix`; text-fact payloads retain the B3 old choice and add only the matching color sentence ([panel_online_requests.json](/hipilot/sharestorage/lys/CognitiveHijacking_CognitiveDenial/research/decision_evidence_audit/revisions/20260906T145758Z_offline_panel/panel_online_requests.json:50), [panel_online_requests.json](/hipilot/sharestorage/lys/CognitiveHijacking_CognitiveDenial/research/decision_evidence_audit/revisions/20260906T145758Z_offline_panel/panel_online_requests.json:91)).
- First-turn system/user templates are exact transformations of retry1; state goals occur consistently and no offline expected label/factor metadata enters model payloads. Existing tests cover this narrow offline projection and logged six passes ([test_offline_preparation.py](/hipilot/sharestorage/lys/CognitiveHijacking_CognitiveDenial/research/decision_evidence_audit/revisions/20260906T145758Z_offline_panel/test_offline_preparation.py:47), [offline_tests.log](/hipilot/sharestorage/lys/CognitiveHijacking_CognitiveDenial/research/decision_evidence_audit/revisions/20260906T145758Z_offline_panel/offline_tests.log:1)).
- Actual maximum is 72 panel calls, plus one two-image witness; 80 calls and 200 transitions are adequate only with the declared “leave remainder unrun” behavior ([EXPERIMENT_PLAN.md](/hipilot/sharestorage/lys/CognitiveHijacking_CognitiveDenial/research/decision_evidence_audit/revisions/20260906T145758Z_offline_panel/EXPERIMENT_PLAN.md:75)).
- Asset review remains correctly bounded: seven asset-level candidates, only four formally scored, three legacy, and zero shell render/submission validations ([proposed_split.json](/hipilot/sharestorage/lys/CognitiveHijacking_CognitiveDenial/research/decision_evidence_audit/revisions/20260906T145758Z_offline_panel/asset_review/proposed_split.json:6)). Direct inspection of all 14 primary images supports the documented visible-evidence caveats; runtime eligibility remains unverified.

Required before authorization:

1. Implement and test the recorded-model boundary projection for **every round**, not only generated first turns. Preserve the real initial choice outside model-visible context for `changed`, fallback, and execution. Current B3 initializes/falls back from `checkpoint.current_selection`; blanking that checkpoint can yield an empty recommendation ([policies.py](/hipilot/sharestorage/lys/CognitiveHijacking_CognitiveDenial/research/decision_evidence_audit/policies.py:265), [EXPERIMENT_PLAN.md](/hipilot/sharestorage/lys/CognitiveHijacking_CognitiveDenial/research/decision_evidence_audit/revisions/20260906T145758Z_offline_panel/EXPERIMENT_PLAN.md:48)).
2. Implement persistence before calls/actions: request, raw response/error, parsed label, fallback status, real initial choice, select/no-op, POST receipt, timestamps, attempt ID, and charged budget. Retention is currently a plan promise, not runner code ([EXPERIMENT_PLAN.md](/hipilot/sharestorage/lys/CognitiveHijacking_CognitiveDenial/research/decision_evidence_audit/revisions/20260906T145758Z_offline_panel/EXPERIMENT_PLAN.md:50)).
3. Re-freeze a factor-interleaved block schedule before sampling. Current fixed 01–08 order places every magenta state before every orange state; cyclic condition order does not remove color/time confounding ([EXPERIMENT_PLAN.md](/hipilot/sharestorage/lys/CognitiveHijacking_CognitiveDenial/research/decision_evidence_audit/revisions/20260906T145758Z_offline_panel/EXPERIMENT_PLAN.md:52)).
4. Record the eventual runtime version separately: current `models.py` and `runner.py` do not match the reference-run record ([raw_failure_audit.json](/hipilot/sharestorage/lys/CognitiveHijacking_CognitiveDenial/research/decision_evidence_audit/revisions/20260906T145758Z_offline_panel/raw_failure_audit.json:33)).

Acknowledged limitations:

- `B3_current` is B3 prompt/logic on a neutral synthetic fixture, not an exact historical replay: its current image omits the old-choice pixels present historically. Thus it tests bundled textual state/prefix sensitivity, not the full three-channel historical cue.
- Color remains confounded with option order, rule-clause position, and—unless fixed—time. Hidden correct/wrong pairs are four duplicated model inputs, not eight independent judgments.
- Independent versus text-fact changes both old-choice visibility and supplied color fact; only B3 versus text-fact isolates added text. No internal-belief inference is licensed.
- Identical current/dashboard images cannot test panel-role ordering; the separately budgeted ordered-image witness is necessary for that claim.
- Natural-task qualification, 112-transition mock checks, natural trajectories, and D0/D1/D2 remain separate, unrun stages ([EXPERIMENT_TRACKER.md](/hipilot/sharestorage/lys/CognitiveHijacking_CognitiveDenial/research/decision_evidence_audit/revisions/20260906T145758Z_offline_panel/EXPERIMENT_TRACKER.md:7)).
