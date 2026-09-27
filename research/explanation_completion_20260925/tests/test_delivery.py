"""Offline renderer unit checks, not fabricated live results."""
import importlib.util
from pathlib import Path


SPEC = importlib.util.spec_from_file_location("completion_delivery", Path(__file__).parents[1] / "delivery.py")
delivery = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(delivery)


def test_untrusted_model_content_is_escaped():
    attack = '<script>alert("x")</script><img src=x onerror=alert(1)>'
    html = delivery.paragraph(attack)
    assert '<script>' not in html and '<img' not in html
    assert '&lt;script&gt;' in html and '&lt;img' in html
    assert '<script>' not in delivery.json_block("source", {"value": attack})


def test_pending_and_disputed_are_not_success_badges():
    assert 'class="badge pending"' in delivery.badge("pending")
    assert 'class="badge pending"' in delivery.badge("disputed")
    assert "待定" in delivery.badge("pending")
    assert "存在分歧" in delivery.badge("disputed")
    assert "仅解释规则维度有支持" in delivery.badge("active")


def test_missing_chinese_notes_are_explicit():
    assert "尚未补充" in delivery.note_block(None)
    assert "非人工确认；不是额外 API 模型输出" in delivery.note_block(["离线翻译说明"])


def test_chain_keeps_observations_rule_conditions_and_null_conclusion():
    rule = {"id": "r2", "text": "If height encodes quantity", "conditions": "only if shared scale", "component": "height"}
    chain = {"chain_id": "base_c2", "rule_id": "r2", "observations": [
        {"ref": "chart_1", "location": "top", "content": "blue above green"}],
        "claim": "possible interpretation", "claim_kind": "underdetermined", "option_label": None}
    view = delivery.chain_card(chain, [rule])
    for value in ("base_c2", "blue above green", "If height encodes quantity", "only if shared scale", "possible interpretation", "未给出（null）"):
        assert value in view


def test_verification_dimensions_remain_separate():
    check = {"target_id": "base_c1", "O": {"status": "refuted", "reason": "wrong literal", "evidence": []},
             "B": {"status": "supported", "reason": "applicable rule", "evidence": []},
             "implication": {"status": "undetermined", "reason": "no conclusion", "evidence": []}}
    view = delivery.verification_card(check)
    assert view.count('class="dimension"') == 3
    assert "wrong literal" in view and "applicable rule" in view and "no conclusion" in view
    assert "被否定（模型核验）" in view and "尚不能确定" in view


def test_case_view_preserves_same_action_chains_and_zero_new_is_not_failure():
    # In-memory interface fixture only; no live-run artifacts are created.
    rules = [{"id": "r1", "text": "rule one", "conditions": "scope", "component": "x"},
             {"id": "r2", "text": "rule two", "conditions": "scope", "component": "x"}]
    chains = [{"chain_id": "base_c" + str(i), "rule_id": "r" + str(i), "observations": [],
               "claim": "separate interpretation " + str(i), "option_label": "same action"} for i in (1, 2)]
    case = {"task_id": "fixture_only", "inputs": {"task": {}, "base_arguments": {"rules": rules, "chains": chains}},
            "result": {"questions": {"questions": [], "summary": "fixture"},
                       "supplement": {"new_chains": [], "new_rules": [], "refinements": [], "question_responses": []}},
            "rule_state": None}
    view = delivery.case_markdown(case, {})
    assert "解释链 base_c1" in view and "解释链 base_c2" in view
    assert "separate interpretation 1" in view and "separate interpretation 2" in view
    assert "新增 0 条并不是失败" in view
    assert "没有生成持久化规则文件" in view


def test_helper_parses_all_case_headings_after_multiline_json():
    helper_path = delivery.PROJECT / ".agents/skills/render-html/scripts/render_html.py"
    spec = importlib.util.spec_from_file_location("completion_render_test_helper", helper_path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    rule = {"id": "r1", "text": "fixture rule", "conditions": "condition", "component": "component"}
    chain = {"chain_id": "base_c1", "rule_id": "r1", "observations": [], "claim": "fixture claim", "option_label": None}
    cases = [{"task_id": cid,
              "inputs": {"task": {}, "base_arguments": {"rules": [rule], "chains": [chain]}},
              "result": {"questions": {"questions": [], "summary": "fixture"},
                         "supplement": {"new_chains": [], "new_rules": [], "refinements": [], "question_responses": []}},
              "rule_state": None} for cid in delivery.CASE_IDS]
    bundle = {"summary": {}, "notes_zh": {}, "cases": cases, "source_sha256": {}}
    source = delivery.source_markdown(bundle)
    blocks = helper.parse_blocks(source.splitlines())
    headings = [block for block in blocks if block["type"] == "heading"]
    texts = [heading["text"] for heading in headings]
    for cid in delivery.CASE_IDS:
        assert cid + " · 解释集合补齐" in texts
        assert cid + " · 任务与原图" in texts
        for title in ("1 初始全部解释", "2 反问检查遗漏", "3 补齐／已有覆盖／未解决", "4 逐维核验", "5 持久化规则状态", "6 阶段回执与原始记录"):
            assert cid + " · " + title in texts
    assert "文件来源与完整数据" in texts
    assert len(headings) == 27
