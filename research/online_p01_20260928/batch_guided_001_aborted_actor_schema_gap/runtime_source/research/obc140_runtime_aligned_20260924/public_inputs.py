"""Project public text from archived non-review HTML, never raw task specs.

This is an explicitly static, three-page task-context protocol. DOM labels are
copied, not neutralized by string rewriting. Files and element selectors live in
an offline sidecar. Hidden input values, option tokens and source attributes do
not enter the model context.
"""
from __future__ import annotations

import re
from collections import Counter
from bs4 import BeautifulSoup

VERSION = "runtime_dom_public_v1"
PUBLIC_KEYS = {"task_alias", "page_title", "user_goal", "chart_reference",
               "primary_field_label", "option_labels", "companion_fields",
               "completion_label", "policy_tables", "page_instructions"}
PRIVATE_KEYS = {"gold", "ground_truth", "correct_value", "correct_action_id",
                "expected_action_id", "misleader_type", "misleading_context",
                "rationale", "csv_path", "source_csv", "misleading_action_ids",
                "scoring_outcome", "error_attribution", "role", "action_space",
                "condition", "spec", "workflow_spec", "workflow_instruction",
                "action_id", "outcome", "evaluation_hidden_from_agent"}


def text(node):
    return node.get_text(" ", strip=True) if node is not None else ""


def visible_soup(markup):
    soup = BeautifulSoup(markup, "html.parser")
    for node in list(soup.select("script, style, template, noscript, [hidden], [aria-hidden='true'], input[type='hidden']")):
        if node.parent is not None:
            node.decompose()
    for node in list(soup.select("[style]")):
        style = re.sub(r"\s+", "", node.get("style", "")).lower()
        if "display:none" in style or "visibility:hidden" in style:
            node.decompose()
    return soup


def assert_public(value):
    if isinstance(value, dict):
        forbidden = set(value) & PRIVATE_KEYS
        if forbidden:
            raise ValueError("private keys in public projection: " + repr(sorted(forbidden)))
        for child in value.values():
            assert_public(child)
    elif isinstance(value, list):
        for child in value:
            assert_public(child)


def extract(pages, alias):
    """Return (public, offline DOM bindings); only supplied HTML is inspected."""
    if set(pages) != {"home", "dashboard", "form"}:
        raise ValueError("Expected exactly the three original public pages")
    soups = {page: visible_soup(markup) for page, markup in pages.items()}
    home, form = soups["home"], soups["form"]
    for name, soup in soups.items():
        if soup.select_one(".chart-compare"):
            raise ValueError("review/compare UI is not an online source: " + name)
    source = {}

    def bind(path, value, page, selector):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Missing public text: " + path)
        source[path] = {"page": page, "selector": selector, "text": value}
        return value

    title = bind("page_title", text(form.title), "form", "title")
    goal_node = home.select_one("main p.instruction") or home.select_one("main section > p")
    goal_selector = "main p.instruction" if home.select_one("main p.instruction") else "main section > p"
    goal = bind("user_goal", text(goal_node), "home", goal_selector)
    image = form.select_one("main img")
    if image is None or len(form.select("main img")) != 1:
        raise ValueError("Expected exactly one chart reference in original form")
    reference_node = image.find_parent("section").find("p")
    reference = bind("chart_reference", text(reference_node), "form", "main section:first-of-type p")
    primary = form.select_one("select#primary_action")
    if primary is None:
        raise ValueError("No original primary action select")
    label = bind("primary_field_label", text(form.select_one("label[for='primary_action']")),
                 "form", "label[for='primary_action']")
    options = []
    for dom_index, option in enumerate(primary.find_all("option")):
        if not option.get("value", "") or option.has_attr("disabled"):
            continue
        if option.has_attr("selected"):
            raise ValueError("Original page has a nonempty preselected primary action")
        options.append(bind("option_labels." + str(len(options)), text(option), "form",
                            "select#primary_action option:nth-of-type(%d)" % (dom_index + 1)))
    if not options or len(options) != len(set(options)):
        raise ValueError("Missing or duplicate primary option labels")
    first = primary.find("option")
    if first is not None and first.get("value", "") and not primary.select("option[selected]"):
        raise ValueError("Browser default would select a nonempty primary action")
    submits = form.select("form button[type='submit']")
    if len(submits) != 1:
        raise ValueError("Expected one public business submission button")
    completion = bind("completion_label", text(submits[0]), "form", "form button[type='submit']")
    companions = []
    for element in form.select("form input, form select, form textarea"):
        if element.get("id") == "primary_action":
            continue
        kind = element.get("type", "text") if element.name == "input" else element.name
        if kind in {"submit", "reset", "button"}:
            continue
        field_id = element.get("id") or element.get("name")
        if not field_id:
            raise ValueError("Unnamed visible form control")
        label_node = form.find("label", attrs={"for": element.get("id")})
        if label_node is None:
            raise ValueError("Visible control has no associated label: " + field_id)
        row = {"field": field_id, "label": text(label_node), "type": kind,
               "required": element.has_attr("required"), "readonly": element.has_attr("readonly")}
        prefix = "companion_fields.%d" % len(companions)
        bind(prefix + ".label", row["label"], "form", "label[for='%s']" % element.get("id"))
        selector = "[id='%s']" % element.get("id")
        if kind == "select":
            all_options = element.find_all("option")
            row["options"] = []
            for index, option in enumerate(all_options):
                row["options"].append({"label": text(option), "disabled": option.has_attr("disabled"),
                                       "selected": option.has_attr("selected") or
                                       (not element.select("option[selected]") and index == 0)})
                bind(prefix + ".options.%d.label" % index, text(option), "form",
                     selector + " option:nth-of-type(%d)" % (index + 1))
        else:
            row["value"] = text(element) if kind == "textarea" else element.get("value", "")
            if kind in {"checkbox", "radio"}:
                row["checked"] = element.has_attr("checked")
            if row["value"]:
                source[prefix + ".value"] = {"page": "form", "selector": selector,
                                             "text": row["value"], "attribute": None if kind == "textarea" else "value"}
            if element.get("placeholder"):
                row["placeholder"] = element["placeholder"]
                source[prefix + ".placeholder"] = {"page": "form", "selector": selector,
                                                   "text": row["placeholder"], "attribute": "placeholder"}
        companions.append(row)
    # Context is visible text, not a hidden backing input or a correct_value.
    for index, block in enumerate(form.select(".readonly-field")):
        row = {"field": "visible_context_%d" % len(companions), "type": "readonly", "required": False,
               "readonly": True, "label": text(block.find("label")), "value": text(block.select_one(".readonly-value"))}
        prefix = "companion_fields.%d" % len(companions)
        source[prefix + ".label"] = {"page": "form", "selector": ".readonly-field", "element_index": index,
                                      "child_selector": "label", "text": row["label"]}
        source[prefix + ".value"] = {"page": "form", "selector": ".readonly-field", "element_index": index,
                                      "child_selector": ".readonly-value", "text": row["value"]}
        if not row["label"] or not row["value"]:
            raise ValueError("Incomplete visible readonly context")
        companions.append(row)
    for index, term in enumerate(form.select("main dl dt")):
        value = term.find_next_sibling("dd")
        row = {"field": "visible_context_%d" % len(companions), "type": "readonly", "required": False,
               "readonly": True, "label": text(term), "value": text(value)}
        prefix = "companion_fields.%d" % len(companions)
        bind(prefix + ".label", row["label"], "form", "main dl dt:nth-of-type(%d)" % (index + 1))
        bind(prefix + ".value", row["value"], "form", "main dl dd:nth-of-type(%d)" % (index + 1))
        companions.append(row)
    policies = []
    for table_index, table in enumerate(form.select("main table")):
        headers = [text(node) for node in table.select("thead th")]
        rows = [[text(node) for node in row.select("td")] for row in table.select("tbody tr")]
        container = table.find_parent(class_=re.compile(r"^policy"))
        policy = {"title": text(container.find("h3")) if container else "",
                  "headers": headers, "rows": rows}
        policies.append(policy)
        for group, values in (("headers", headers), ("rows", rows)):
            for index, value in enumerate(values):
                if group == "headers":
                    bind("policy_tables.%d.headers.%d" % (table_index, index), value, "form",
                         "main table:nth-of-type(%d) thead th:nth-of-type(%d)" % (table_index + 1, index + 1))
                else:
                    for cell, string in enumerate(value):
                        bind("policy_tables.%d.rows.%d.%d" % (table_index, index, cell), string, "form",
                             "main table:nth-of-type(%d) tbody tr:nth-of-type(%d) td:nth-of-type(%d)" % (table_index + 1, index + 1, cell + 1))
        if policy["title"]:
            source["policy_tables.%d.title" % table_index] = {"page": "form", "selector": "main table",
                "element_index": table_index, "parent_policy_heading": True, "text": policy["title"]}
    instructions = []
    for page, soup in soups.items():
        for index, node in enumerate(soup.select("main p")):
            value = text(node)
            if value:
                pos = len(instructions)
                instructions.append({"page": page, "text": value})
                source["page_instructions.%d.text" % pos] = {"page": page, "selector": "main p",
                                                             "element_index": index, "text": value}
    public = {"task_alias": alias, "page_title": title, "user_goal": goal,
              "chart_reference": reference, "primary_field_label": label,
              "option_labels": options, "companion_fields": companions,
              "completion_label": completion, "policy_tables": policies,
              "page_instructions": instructions}
    if set(public) != PUBLIC_KEYS:
        raise ValueError("Projection keys differ from contract")
    assert_public(public)
    return public, source


def get_path(value, path):
    for part in path.split("."):
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def verify_bindings(public, bindings, pages):
    soups = {page: visible_soup(markup) for page, markup in pages.items()}
    for path, binding in bindings.items():
        matches = soups[binding["page"]].select(binding["selector"])
        node = matches[binding.get("element_index", 0)]
        if binding.get("child_selector"):
            node = node.select_one(binding["child_selector"])
        if binding.get("parent_policy_heading"):
            node = node.find_parent(class_=re.compile(r"^policy")).find("h3")
        actual = node.get(binding["attribute"]) if binding.get("attribute") else text(node)
        if actual != binding["text"] or actual != get_path(public, path):
            raise ValueError("DOM/public binding mismatch: " + path)
    return len(bindings)


WARNING_PATTERNS = {
    "explicit_mechanism_word": r"\b(?:misleading|deceptive|distorted|reversed|inverted|truncated)\b",
    "evidence_channel_priority": r"\b(?:rather than|instead of|labeled (?:rating|data)|mislabeled_value)\b",
}


def text_leaves(value, prefix=""):
    if isinstance(value, str):
        yield prefix, value
    elif isinstance(value, dict):
        for key, child in value.items():
            yield from text_leaves(child, (prefix + "." + key).lstrip("."))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from text_leaves(child, prefix + "." + str(index))


def advisory_flags(public):
    """Never edits inputs or judges correctness; inspect matches in their context."""
    flags = []
    for path, value in text_leaves(public):
        for kind, pattern in WARNING_PATTERNS.items():
            if re.search(pattern, value, flags=re.I):
                flags.append({"kind": kind, "field": path, "text": value,
                              "status": "review_needed_original_visible_text_retained"})
    return flags
