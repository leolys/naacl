"""Offline primary-artifact inspection and panel preparation. No model/browser API."""
import ast
import hashlib
import itertools
import json
from collections import Counter
from fractions import Fraction
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PACKAGE = ROOT / "research/decision_evidence_audit"
OLD = PACKAGE / "revisions/20260906T1342Z"
RUN = PACKAGE / "runs/stage2_live_smoke_20260906T1342Z"


def read(path):
    return json.loads(path.read_text())


def relative(path):
    return str(path.relative_to(ROOT))


def save(path, data):
    # New files only; rerunning cannot overwrite the prepared panel or raw runs.
    with path.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def main():
    # Reuse existing run provenance, not a new hash/contract scheme.
    manifest = read(RUN / "run_manifest.json")
    version = []
    for entry in manifest["code_fingerprint"]["files"]:
        path = ROOT / entry["path"]
        version.append({"path": entry["path"], "matches_existing_run_record":
                        hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]})
    assert next(v for v in version if v["path"].endswith("/policies.py"))["matches_existing_run_record"]
    # Extract ONLY the original pure parser AST; avoid importing newer runner/client code.
    tree = ast.parse((PACKAGE / "policies.py").read_text())
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_b3_output")
    namespace = {}
    exec("import json, re, math\nfrom typing import Any", namespace)
    exec(compile(ast.Module(body=[node], type_ignores=[]), "historical_b3_parser", "exec"), namespace)
    parse = namespace["_b3_output"]
    cases = []
    for attempt in ("live_controls", "live_controls_retry1"):
        for name in ("visible_revision", "correct_keep", "injected_two_crop_transport"):
            case = OLD / attempt / name
            result = read(case / "result.json")
            exchanges = []
            for request_path in sorted((case / "policy/requests").glob("*.json")):
                request = read(request_path)
                response = read(case / "policy/responses" / request_path.name)
                images = []
                for artifact in request["image_artifacts"]:
                    path = case / "policy" / artifact
                    with Image.open(path) as im:
                        rgb = im.convert("RGB")
                        images.append({"path": relative(path), "size": list(im.size),
                                       "center_rgb": list(rgb.getpixel((im.width // 2, im.height // 2))),
                                       "rgb_counts": [[list(k), v] for k, v in Counter(rgb.getdata()).most_common(3)]})
                kind, parsed, error = parse(response["text"])
                exchanges.append({"request_path": relative(request_path), "request": request,
                                  "response": response, "images": images,
                                  "parser_kind": kind, "parsed": parsed, "parser_error": error})
            final = exchanges[-1]
            policy = result["policy"]
            assert final["parsed"]["option_label"] == policy["recommended_option"]
            assert policy["changed"] == (policy["recommended_option"] != policy["original_selection"])
            assert (case / "dashboard.png").read_bytes() == (case / "policy/observations/observed_00.png").read_bytes()
            assert (case / "current.png").read_bytes() == (case / "policy/observations/observed_current.png").read_bytes()
            cases.append({"attempt": attempt, "name": name, "recorded_result": result,
                          "exchanges": exchanges, "raw_label_equals_parsed_and_recommended": True,
                          "browser_execution_present": False})
    b4 = []
    for unit in ("unit_0012", "unit_0016"):
        folder = RUN / "online/units" / unit
        b4.append({"unit": unit, "result": read(folder / "result.json"),
                   "requests": [read(p) for p in sorted((folder / "requests").glob("*.json"))],
                   "responses": [read(p) for p in sorted((folder / "responses").glob("*.json"))]})
    # Algebraic exhaustive finite check is not a model test or empirical equivalence claim.
    for x, y, z in itertools.product(range(-5, 6), repeat=3):
        for comparison in (lambda a, b: a > b, lambda a, b: a == b, lambda a, b: a < b):
            assert comparison(x, Fraction(y + z, 2)) == comparison(x, Fraction(x + y + z, 3))
    save(HERE / "raw_failure_audit.json", {"reference_run": RUN.name, "source_record_comparison": version,
         "cases": cases, "env025_b4": b4, "new_model_calls": 0, "new_browser_transitions": 0,
         "mean_equivalence_checks": 3 * 11**3, "semantic_pass_claim": False})

    image_dir = HERE / "panel_images"
    image_dir.mkdir(exist_ok=False)
    for color_index, color in enumerate(((255, 0, 255), (255, 165, 0))):
        for role_index, role in enumerate(("current", "dashboard")):
            with Image.new("RGB", (512, 384), "white") as im:
                draw = ImageDraw.Draw(im)
                draw.text((20, 16), "Panel color routing", fill="black")
                draw.rectangle((20, 60, 490, 350), fill=color)
                im.save(image_dir / f"image_{color_index * 2 + role_index + 1:02d}.png")

    template = read(OLD / "live_controls_retry1/visible_revision/policy/requests/request_0001.json")
    template_context = json.dumps(template["public_context"], ensure_ascii=False)
    assert template_context in template["user_prompt"]
    original_goal = template["public_context"]["user_goal"]
    states, units, online = [], [], []
    modes = ["B3_current", "independent_hidden_selection", "B3_with_text_color_fact"]
    for c, m, wrong in itertools.product(range(2), repeat=3):
        color = ("magenta", "orange")[c]
        mapping = {"magenta": ("Route A", "Route B")[m], "orange": ("Route B", "Route A")[m]}
        expected = mapping[color]
        initial = ("Route B" if expected == "Route A" else "Route A") if wrong else expected
        goal = f"Choose {mapping['magenta']} when the large dashboard rectangle is magenta; choose {mapping['orange']} when it is orange."
        options = ["Route A", "Route B"] if c == 0 else ["Route B", "Route A"]
        state_id = f"state_{len(states) + 1:02d}"
        image_refs = [f"panel_images/image_{c * 2 + r + 1:02d}.png" for r in range(2)]
        states.append({"state_id": state_id, "fixture_color": color, "public_mapping": mapping,
                       "user_goal": goal, "initial_selection": initial, "initial_correct": not wrong,
                       "expected_option_offline_only": expected, "visible_options": options,
                       "images": image_refs, "state_origin": "injected_synthetic_not_natural"})
        # Rotate mode order without adding experimental cells or extra output draws.
        offset = (len(states) - 1) % 3
        for mode in modes[offset:] + modes[:offset]:
            context = {**template["public_context"], "user_goal": goal, "current_selection": initial,
                       "visible_options": options, "visible_action_prefix": [
                           {"action": "select_option", "select_name": "route", "option_text": initial}]}
            if mode == "independent_hidden_selection":
                context["current_selection"] = ""
                context["visible_action_prefix"] = []
            if mode == "B3_with_text_color_fact":
                context["diagnostic_color_fact"] = f"The large dashboard rectangle is {color}."
            # Exactly retain historical system and user template; only input facts vary.
            user = template["user_prompt"].replace(template_context, "__CONTEXT__").replace(original_goal, goal)
            user = user.replace("__CONTEXT__", json.dumps(context, ensure_ascii=False))
            unit_id = f"unit_{len(units) + 1:02d}"
            units.append({"unit_id": unit_id, "state_id": state_id, "mode": mode,
                          "status": "not_run_awaiting_explicit_authorization"})
            online.append({"unit_id": unit_id, "state_id": state_id, "mode": mode,
                           "model_payload": {"system_prompt": template["system_prompt"], "user_prompt": user,
                                             "image_artifacts": image_refs, "public_context": context}})
    assert len(states) == 8 and len(units) == 24
    assert sum(s["visible_options"][0] == "Route A" for s in states) == 4
    assert sum(s["expected_option_offline_only"] == s["visible_options"][0] for s in states) == 4
    assert sum(s["initial_selection"] == s["visible_options"][0] for s in states) == 4
    # For each color/rule pair, blinding removes ALL old-selection dependence from first inputs.
    hidden = [u["model_payload"] for u in online if u["mode"] == "independent_hidden_selection"]
    assert all(hidden[i] == hidden[i + 1] for i in range(0, 8, 2))
    assert all("expected_option_offline_only" not in json.dumps(u["model_payload"]) for u in online)
    save(HERE / "control_panel.json", {"version": "offline_panel_v1", "reference_run": RUN.name,
         "execution_state_order": ["state_01", "state_06", "state_04", "state_07", "state_02", "state_05", "state_03", "state_08"],
         "execution_rule": "Follow execution_state_order; within each state retain the recorded units order. JSON state/units arrays are enumeration, not runtime scheduling.",
         "schedule_revision": "pre_sampling_review_1_no_model_outputs_used",
         "states": states, "units": units, "unit_count": 24, "model_calls_per_unit_max": 3,
         "observations_per_unit_max": 2, "option_order_note": "4 AB / 4 BA, paired initial states same order; color/order confounded, so no independent color/order-effect claim.",
         "hidden_condition_unique_first_inputs": 4, "model_service_start_authorized": False})
    save(HERE / "panel_online_requests.json", online)
    print("OFFLINE_PREPARATION_OK 6 historical cases; raw-label equality 6/6; 3993 arithmetic checks; 8 states; 24 pending units; 0 new model calls; 0 browser transitions")


if __name__ == "__main__":
    main()
