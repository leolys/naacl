#!/usr/bin/env python3
"""Run the paired clean/misleading travel sample with main-experiment agents."""

from __future__ import annotations

import argparse
import signal
from pathlib import Path

import run_travel_three_version_agents as base


REPO_ROOT = Path(__file__).resolve().parents[2]
PAIR_ROOT = REPO_ROOT / "travel_choose_confirm_review_sample"
DEFAULT_OUTPUT_ROOT = (
    REPO_ROOT
    / "web_agent_benchmark"
    / "pair_evaluation_records"
    / "travel_choose_confirm_pair_available_main_models_20260712"
)

PAIR_CONDITIONS = (
    base.TravelVersion(
        "misleading",
        PAIR_ROOT,
        "misleading.jsonl",
        start_path="/travel/",
    ),
    base.TravelVersion(
        "clean",
        PAIR_ROOT,
        "clean.jsonl",
        start_path="/travel-clean/",
    ),
)


def configure_base() -> None:
    base.SUITE_ROOT = PAIR_ROOT
    base.VERSIONS = PAIR_CONDITIONS
    base.VERSION_BY_ID = {condition.version_id: condition for condition in PAIR_CONDITIONS}
    base.MODELS.update(
        {
            "gemini31flash_image_preview": base.ModelSpec(
                "gemini31flash_image_preview",
                "gemini_3_1_flash_image_preview_temp0_top_p1_seed12345",
                "Gemini 3.1 Flash Image Preview",
                "gemini-3.1-flash-image-preview",
                2048,
            ),
            "gemini3pro_image_preview": base.ModelSpec(
                "gemini3pro_image_preview",
                "gemini_3_pro_image_preview_temp0_top_p1_seed12345",
                "Gemini 3 Pro Image Preview",
                "gemini-3-pro-image-preview",
                2048,
            ),
            "qwen35plus_litellm": base.ModelSpec(
                "qwen35plus_litellm",
                "qwen3_5_plus_temp0_top_p1_seed12345",
                "Qwen3.5 Plus",
                "qwen3.5-plus",
                1024,
            ),
            "qwen36plus_litellm": base.ModelSpec(
                "qwen36plus_litellm",
                "qwen3_6_plus_temp0_top_p1_seed12345",
                "Qwen3.6 Plus",
                "qwen3.6-plus",
                1024,
            ),
            "kimik26_litellm": base.ModelSpec(
                "kimik26_litellm",
                "kimik2_6_temp0_top_p1_seed12345",
                "Kimi K2.6",
                "kimi-k2.6",
                8192,
            ),
        }
    )


def main() -> int:
    configure_base()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", default="all")
    parser.add_argument("--versions", default="all")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--port-base", type=int, default=52141)
    parser.add_argument("--max-steps", type=int, default=10)
    parser.add_argument(
        "--aime-base-url",
        default="https://aimemodeldev.myhexin.com/litellm/v1",
    )
    parser.add_argument(
        "--aime-api-style",
        choices=("chat_completions", "responses", "messages"),
        default="messages",
    )
    parser.add_argument("--aime-max-retries", type=int, default=2)
    parser.add_argument("--aime-request-delay-sec", type=float, default=2)
    parser.add_argument("--aime-read-timeout-sec", type=float, default=300)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--top-p", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=12345)
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.port_base <= 65534:
        raise SystemExit("--port-base must be between 1 and 65534")

    def handle_termination(_signum: int, _frame: object) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, handle_termination)
    return_code = base.run(args)
    summary_path = args.output_root.resolve() / "summary.md"
    if summary_path.exists():
        summary = summary_path.read_text(encoding="utf-8")
        summary = summary.replace(
            "# Travel Three-Version Agent Evaluation Summary",
            "# Travel Choose-Confirm Paired Agent Evaluation Summary",
            1,
        )
        summary = summary.replace("## By Version", "## By Condition", 1)
        summary = summary.replace("| Version | Outcomes |", "| Condition | Outcomes |", 1)
        summary = summary.replace(
            "| Model | Version | Outcome | Error | Recovered |",
            "| Model | Condition | Outcome | Error | Recovered |",
            1,
        )
        summary_path.write_text(summary, encoding="utf-8")
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
