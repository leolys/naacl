"""One fixed, non-chart interface check per backbone; never tune on panel tasks."""
from pathlib import Path

from PIL import Image

from research.decision_evidence_audit import core, runner
from .harness import TransitionScope, capture_pending, run_branch


def route_task():
    return dict(task_alias="control", page_title="Route control", user_goal="Choose Route A and submit.",
                chart_reference="No chart interpretation required.", primary_field_label="Route",
                option_labels=["Route A", "Route B"])


def qualify(browser, model, view, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    view.section = "controls"
    blank = directory / "blank.png"
    Image.new("RGB", (300, 180), "white").save(blank)
    results = []
    # Same real actor/hook/executor as the panel, with a publicly explicit target.
    for target in ("Route A", "Route B"):
        for initial in ("Route A", "Route B"):
            task = route_task()
            task["user_goal"] = f"Choose {target} and submit."
            root = directory / f"route_{target[-1]}_{initial[-1]}"
            submissions = root / "server_receipts.jsonl"
            with runner.managed_shell(task, blank, submissions) as server:
                page = browser.new_page(viewport=dict(width=1440, height=1100))
                executor = runner.BrowserExecutor(page, ledger=TransitionScope(view), task_alias="control")
                try:
                    executor.navigate(server.base_url + "/task/control", phase="control_setup")
                    for action in (dict(action="click_link", text="Open Dashboard"),
                                   dict(action="click_link", text="Open Form"),
                                   dict(action="select_option", select_name="primary_action", option_text=initial)):
                        executor.execute(action, phase="control_setup")
                    cp, prefix = capture_pending(page, executor, model, goal=task["user_goal"], alias="control",
                                                 directory=root / "prefix", max_calls=2)
                    branch = None if cp is None else run_branch(page, executor, model, cp, strategy="B0",
                        directory=root / "B0", prefix_receipts=executor.receipts[:], submission_path=submissions)
                    passed = bool(branch and branch["submitted"] and branch["confirmation_observed"]
                                  and branch["server_receipts"][0]["selected_option_label"] == target)
                    results.append(dict(kind="nonchart_public_route", target=target, initial=initial,
                                        passed=passed, prefix=prefix, branch=branch))
                finally:
                    core.write_json(root / "execution_receipts.json", executor.receipts)
                    page.close()
                    core.write_json(directory / "results.json", results)
                if not passed:
                    raise RuntimeError("public-route interface control failed; panel not started")
    images = []
    for color in ("red", "blue"):
        path = directory / f"{color}.png"
        Image.new("RGB", (180, 120), color).save(path)
        images.append(path)
    # Reversed order distinguishes two real image inputs from last-image-only service behavior.
    for index, ordered in enumerate((images, list(reversed(images)))):
        request_dir, response_dir = directory / "multi_image" / "requests", directory / "multi_image" / "responses"
        reply = model.call(phase="multi_image_control",
            system_prompt='Return only JSON: {"colors": ["first image color", "second image color"]}.',
            user_prompt="Name the two solid image colors in their supplied order, using red or blue.",
            image_path=ordered, image_artifact=[str(p.relative_to(directory)) for p in ordered],
            public_context={"user_goal": "Name the two supplied image colors in order."},
            request_dir=request_dir, response_dir=response_dir)
        try:
            decision = runner._extract_json_object(reply.text)
        except (ValueError, TypeError):
            decision = {}
        passed = isinstance(decision, dict) and decision.get("colors") == (["red", "blue"] if index == 0 else ["blue", "red"])
        results.append(dict(kind="ordered_two_images", order_index=index, passed=passed, response=reply.text))
        core.write_json(directory / "results.json", results)
        if not passed:
            raise RuntimeError("ordered multi-image interface control failed; panel not started")
    return results
