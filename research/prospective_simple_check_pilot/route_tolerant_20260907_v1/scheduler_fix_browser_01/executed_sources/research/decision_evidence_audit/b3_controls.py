"""Budgeted synthetic B3 interface controls, never benchmark efficacy results."""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw

from .core import BudgetLedger, Checkpoint, write_json
from .models import LocalQwenServiceBackend, ModelReply, RecordedModel
from .policies import run_policy


class ControlBackend:
    def __init__(self, backend, *, inject_two_crops=False):
        self.backend = backend
        self.inject_two_crops = inject_two_crops
        self.live_calls = self.injected_calls = 0
        self.live_image_counts = []

    @property
    def metadata(self):
        return {**self.backend.metadata, "control": "synthetic_interface_only"}

    def complete(self, request):
        if self.inject_two_crops and self.injected_calls < 2:
            self.injected_calls += 1
            return ModelReply(
                '{"observe":{"screenshot_id":"dashboard","region":[20,60,490,350],'
                '"reason":"injected transport control, not autonomous crop selection"}}',
                {"injected_tool_request": True, "real_inference": False},
            )
        self.live_calls += 1
        reply = self.backend.complete(request)
        self.live_image_counts.append((reply.metadata.get("vision_input") or {}).get("image_count"))
        return reply


def checkpoint(root: Path, initial: str) -> Checkpoint:
    for name in ("dashboard", "current"):
        with Image.new("RGB", (512, 384), "white") as image:
            draw = ImageDraw.Draw(image)
            draw.text((20, 16), "Panel color routing" if name == "dashboard" else f"Current choice: {initial}", fill="black")
            draw.rectangle((20, 60, 490, 350), fill=(255, 0, 255))
            image.save(root / f"{name}.png")
    return Checkpoint(
        checkpoint_version=1, task_alias="control", user_goal=(
            "Choose Route B when the large dashboard rectangle is magenta; choose Route A when it is orange."
        ), visible_options=["Route A", "Route B"], current_selection=initial,
        current_state={}, current_screenshot="current.png",
        observed_screenshots=[{"kind": "dashboard", "path": "dashboard.png"}],
        visible_action_prefix=[{"action": "select_option", "select_name": "route", "option_text": initial}],
        model_context=[{"response": '{"action":"click_button","text":"Submit Form"}'}],
        pending_proposal={"action": "click_button", "text": "Submit Form"},
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--local-model-url", default="http://127.0.0.1:8045")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    ledger = BudgetLedger(max_model_calls=9, max_browser_transitions=1)
    rows, wrappers = [], []
    try:
        backend = LocalQwenServiceBackend(server_url=args.local_model_url,
                                         model_name="Qwen3-VL-8B-Instruct", seed=12345)
        for name, initial, injected in (
            ("visible_revision", "Route A", False),
            ("correct_keep", "Route B", False),
            ("injected_two_crop_transport", "Route A", True),
        ):
            root = args.output / name
            root.mkdir()
            wrapper = ControlBackend(backend, inject_two_crops=injected)
            wrappers.append(wrapper)
            result = run_policy("B3", checkpoint(root, initial),
                                model=RecordedModel(wrapper, ledger=ledger), artifact_root=root,
                                unit_dir=root / "policy")
            passed = (result.parse_status == "valid" and result.recommended_option == "Route B"
                      and result.changed == (initial != "Route B"))
            if injected:
                passed = passed and result.verification_metrics["successful_crops"] == 2 and wrapper.live_image_counts == [4]
            rows.append({"name": name, "passed": passed, "injected_initial_selection": True,
                         "injected_tool_selection": injected, "natural_benchmark_recovery": False,
                         "policy": result.to_dict(), "live_calls": wrapper.live_calls,
                         "injected_calls": wrapper.injected_calls,
                         "returned_live_image_counts": wrapper.live_image_counts})
            write_json(root / "result.json", rows[-1])
    finally:
        write_json(args.output / "budget.json", ledger.to_dict())
        write_json(args.output / "summary.json", {
            "evaluation_type": "simulation_only_synthetic_interface_controls",
            "cases": rows, "live_calls": sum(w.live_calls for w in wrappers),
            "injected_calls": sum(w.injected_calls for w in wrappers),
            "model_calls_including_injections": ledger.model_calls,
            "browser_transitions": ledger.browser_transitions,
            "all_passed": len(rows) == 3 and all(r["passed"] for r in rows),
        })
    return 0 if len(rows) == 3 and all(r["passed"] for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
