"""Offline checks of the new public DOM projection, not model correctness.

The runtime task index is an offline test oracle only. Neither its private keys
nor its option tokens are supplied to extract(). Fixtures read archived HTML;
no network, model service, hidden answer repair, or business submission occurs.
"""
import copy
import importlib.util
import json
from pathlib import Path

import pytest
from bs4 import BeautifulSoup


MODULE_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = MODULE_ROOT.parents[1]
ARCHIVE = WORKSPACE / ".aris" / "task_flows_20260924"
spec = importlib.util.spec_from_file_location("runtime_public_inputs_tested", MODULE_ROOT / "public_inputs.py")
projection = importlib.util.module_from_spec(spec)
spec.loader.exec_module(projection)
AUDIT = json.loads((ARCHIVE / "RUNTIME_AUDIT.json").read_text(encoding="utf-8-sig"))
RUNTIME = json.loads((ARCHIVE / "RUNTIME_TASKS.json").read_text(encoding="utf-8-sig"))
OFFICIAL = [row for row in RUNTIME if row["arm"] == "official140"]
BY_SLUG = {row["slug"]: row for row in OFFICIAL}


def archived_pages(row):
    root = Path(AUDIT["receipt_dir"]) / (row["domain"] + "_official140")
    return {page: (root / (row["slug"] + "_" + page + ".html")).read_text(encoding="utf-8")
            for page in ("home", "dashboard", "form")}


def minimal_pages(extra="", primary=None):
    primary = primary or '<option value="">Choose route</option><option value="a">Route A</option><option value="b">Route B</option>'
    return {
        "home": '<html><title>Route task</title><main><section><p class="instruction">Inspect the chart and select the matching route.</p></section></main></html>',
        "dashboard": '<main><p>Use the labeled data when applying the public routing threshold.</p></main>',
        "form": '<html><title>Route task</title><main><section><p>Chart reference</p><img src="/chart"></section>'
                '<section><form><label for="primary_action">Route</label><select id="primary_action">' + primary + '</select>'
                + extra + '<button type="submit">Submit Form</button></form></section></main></html>',
    }


def assert_no_private_keys(value):
    if isinstance(value, dict):
        assert not set(value).intersection(projection.PRIVATE_KEYS)
        for child in value.values():
            assert_no_private_keys(child)
    elif isinstance(value, list):
        for child in value:
            assert_no_private_keys(child)


def test_archive_covers_fixed_official_140_without_clean_arm():
    assert len(OFFICIAL) == len(BY_SLUG) == AUDIT["tasks"] == 140
    assert {row["arm"] for row in OFFICIAL} == {"official140"}


@pytest.mark.parametrize("row", OFFICIAL, ids=lambda row: row["slug"])
def test_archived_dom_matches_official_public_title_goal_options_and_bindings(row):
    pages = archived_pages(row)
    public, bindings = projection.extract(pages, "task-" + row["slug"])
    assert public["page_title"] == row["title"]
    assert public["user_goal"] == row["goal"]
    assert set(public) == projection.PUBLIC_KEYS
    assert_no_private_keys(public)
    projection.assert_public(public)
    # Independently parse real DOM: do not inherit extract()'s option filter.
    form = BeautifulSoup(pages["form"], "html.parser")
    select = form.select_one("#primary_action")
    actual = [option for option in select.find_all("option")
              if option.get("value", "") and not option.has_attr("disabled")]
    labels = [option.get_text(" ", strip=True) for option in actual]
    assert public["option_labels"] == labels == [option["label"] for option in row["options"]]
    selected = select.select("option[selected]")
    effective = selected[0] if selected else select.find("option")
    assert effective.get("value", "") == "", "Original browser state must start with no primary choice"
    assert public["completion_label"] == form.select_one("button[type='submit']").get_text(" ", strip=True) == "Submit Form"
    assert projection.verify_bindings(public, bindings, pages) == len(bindings) > 0
    serialized = json.dumps(public, ensure_ascii=False)
    for option in row["options"]:
        assert option["action_id"] not in serialized
        assert option["token"] not in serialized


@pytest.mark.parametrize("slug, forbidden", [
    ("b001", "misleading"),
    ("b002", "tallest-looking"),
    ("pub003", "legend is reversed"),
])
def test_known_old_mechanism_hints_not_reintroduced(slug, forbidden):
    public, _ = projection.extract(archived_pages(BY_SLUG[slug]), "task-" + slug)
    assert forbidden not in (public["page_title"] + " " + public["user_goal"]).lower()
    if slug == "pub003":
        # WV is a real visible option, but must not be a prescribed completion.
        assert any("West Virginia" in label for label in public["option_labels"])
        assert "West Virginia" not in public["completion_label"]
        assert public["completion_label"] == "Submit Form"


def test_hidden_controls_styles_scripts_and_review_metadata_are_not_public():
    pages = minimal_pages('''
        <input type="hidden" name="gold" value="HIDDEN_GOLD_SENTINEL">
        <div hidden><p>HIDDEN_CONTAINER_SENTINEL</p></div>
        <div aria-hidden="true"><p>ARIA_HIDDEN_SENTINEL</p></div>
        <p style="display: none">DISPLAY_NONE_SENTINEL</p>
        <p style="visibility: hidden">VISIBILITY_HIDDEN_SENTINEL</p>
        <script>const correct_action_id = "SCRIPT_SENTINEL";</script>
        <style>.x::after { content: "STYLE_SENTINEL"; }</style>
        <template><p>TEMPLATE_SENTINEL</p></template>
        <noscript><p>NOSCRIPT_SENTINEL</p></noscript>
    ''')
    public, bindings = projection.extract(pages, "fixture")
    serialized = json.dumps([public, bindings])
    assert "SENTINEL" not in serialized
    assert public["companion_fields"] == []
    assert_no_private_keys(public)
    projection.verify_bindings(public, bindings, pages)


def test_readonly_context_uses_displayed_text_not_hidden_backing_value():
    pages = minimal_pages('''
        <input type="hidden" name="region" value="SECRET_BACKING_VALUE">
        <div class="readonly-field"><label>Region</label><div class="readonly-value">Visible North</div></div>
        <label for="quantity">Quantity</label><input id="quantity" type="text" readonly value="15">
        <dl><dt>Review scope</dt><dd>Visible districts</dd></dl>
    ''')
    public, bindings = projection.extract(pages, "fixture")
    values = {field["label"]: field["value"] for field in public["companion_fields"]}
    assert values == {"Region": "Visible North", "Quantity": "15", "Review scope": "Visible districts"}
    assert "SECRET_BACKING_VALUE" not in json.dumps(public)
    assert all(field["readonly"] for field in public["companion_fields"])
    projection.verify_bindings(public, bindings, pages)


def test_companion_dropdown_preserves_placeholder_and_real_default():
    pages = minimal_pages('''
        <label for="required_region">Region</label><select id="required_region" required>
            <option value="" selected disabled>Select value</option><option value="north">North</option>
        </select>
        <label for="implicit_default">Queue</label><select id="implicit_default">
            <option value="standard">Standard</option><option value="urgent">Urgent</option>
        </select>
    ''')
    public, bindings = projection.extract(pages, "fixture")
    fields = {field["field"]: field for field in public["companion_fields"]}
    region = fields["required_region"]
    assert region["required"]
    assert region["options"] == [{"label": "Select value", "disabled": True, "selected": True},
                                  {"label": "North", "disabled": False, "selected": False}]
    assert "value" not in region, "Must not turn sole available option into a completed selection"
    assert fields["implicit_default"]["options"][0]["selected"]
    assert not fields["implicit_default"]["options"][1]["selected"]
    projection.verify_bindings(public, bindings, pages)


def test_visible_public_thresholds_and_labeled_guidance_retained_without_rewriting():
    pages = minimal_pages('''
        <section class="policy-box"><h3>Routing thresholds</h3><table>
        <thead><tr><th>Range</th><th>Action</th></tr></thead><tbody>
        <tr><td>value &gt;= 20</td><td>Route A</td></tr>
        <tr><td>value &lt; 20</td><td>Route B</td></tr></tbody></table></section>
    ''')
    public, bindings = projection.extract(pages, "fixture")
    assert public["policy_tables"] == [{"title": "Routing thresholds", "headers": ["Range", "Action"],
                                         "rows": [["value >= 20", "Route A"], ["value < 20", "Route B"]]}]
    original = "Use the labeled data when applying the public routing threshold."
    assert {"page": "dashboard", "text": original} in public["page_instructions"]
    before = copy.deepcopy(public)
    flags = projection.advisory_flags(public)
    assert public == before, "Advisory review must not silently rewrite original visible guidance"
    assert any(flag["text"] == original for flag in flags)
    projection.verify_bindings(public, bindings, pages)


def test_binding_rejects_changed_public_text_or_changed_source_html():
    pages = minimal_pages()
    public, bindings = projection.extract(pages, "fixture")
    modified = copy.deepcopy(public)
    modified["user_goal"] = "Pick Route A without looking."
    with pytest.raises(ValueError, match="binding mismatch"):
        projection.verify_bindings(modified, bindings, pages)
    changed_pages = dict(pages)
    changed_pages["home"] = pages["home"].replace("Inspect the chart", "Disregard the chart")
    with pytest.raises(ValueError, match="binding mismatch"):
        projection.verify_bindings(public, bindings, changed_pages)


@pytest.mark.parametrize("primary", [
    '<option value="">Choose</option><option value="a" selected>Route A</option><option value="b">Route B</option>',
    '<option value="a">Route A</option><option value="b">Route B</option>',
])
def test_nonempty_initial_primary_state_is_rejected_not_silently_reset(primary):
    with pytest.raises(ValueError, match="preselected|default"):
        projection.extract(minimal_pages(primary=primary), "fixture")


def test_review_compare_markup_is_rejected():
    pages = minimal_pages('<div class="chart-compare">Two arms here</div>')
    with pytest.raises(ValueError, match="review/compare"):
        projection.extract(pages, "fixture")


@pytest.mark.parametrize("key", ["gold", "role", "action_id", "correct_value", "misleader_type", "outcome"])
def test_private_fields_rejected_at_nested_boundary(key):
    with pytest.raises(ValueError, match="private keys"):
        projection.assert_public({"nested": [{key: "do not send"}]})
