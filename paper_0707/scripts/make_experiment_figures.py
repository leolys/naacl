#!/usr/bin/env python3
"""Generate experiment figures for the EMNLP paper draft.

The figures are derived from the final paired clean/misleading evaluation
records, so the plotted values stay synchronized with the paper tables.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[3]
PAIR_RESULTS = (
    REPO_ROOT
    / "web_agent_benchmark/pair_evaluation_records/"
    / "final_selected_merged_20260521_qwen_agent_error_repaired/paired_results.jsonl"
)
STEP_RESULTS = (
    REPO_ROOT
    / "web_agent_benchmark/pair_evaluation_records/"
    / "behavior_efficiency_analysis_final_selected_qwen_agent_error_repaired_20260521/"
    / "paired_step_metrics.jsonl"
)
FIG_DIR = REPO_ROOT / "EMNLP2026/Instructions_for__ACL_Proceedings/figures"


PAIR_MODEL_ORDER = [
    "gpt54",
    "gpt55_litellm",
    "gemini31flash_image_preview",
    "gemini3pro_image_preview",
    "qwen35plus_litellm",
    "qwen36plus_litellm",
    "claude_haiku_4_5_litellm",
    "claude_sonnet_4_6_litellm",
    "claude_opus_4_6_aime_responses",
    "kimik26",
]

STEP_MODEL_ORDER = [
    "gpt54_temp0_top_p1_seed12345",
    "gpt_5_5_litellm_temp0_top_p1_seed12345",
    "gemini_3_1_flash_image_preview_temp0_top_p1_seed12345",
    "gemini_3_pro_image_preview_temp0_top_p1_seed12345",
    "qwen3_5_plus_temp0_top_p1_seed12345",
    "qwen3_6_plus_temp0_top_p1_seed12345",
    "claude_haiku_4_5_litellm_temp0_top_p1_seed12345",
    "claude_sonnet_4_6_litellm_temp0_top_p1_seed12345",
    "claude_opus_4_6_aime_responses_temp0_top_p1_seed12345",
    "kimik2_6_temp0_top_p1_seed12345",
]

MODEL_NAME = {
    "gpt54": "GPT-5.4",
    "gpt55_litellm": "GPT-5.5",
    "gemini31flash_image_preview": "Gemini 3.1 Flash",
    "gemini3pro_image_preview": "Gemini 3 Pro",
    "qwen35plus_litellm": "Qwen 3.5 Plus",
    "qwen36plus_litellm": "Qwen 3.6 Plus",
    "claude_haiku_4_5_litellm": "Claude Haiku 4.5",
    "claude_sonnet_4_6_litellm": "Claude Sonnet 4.6",
    "claude_opus_4_6_aime_responses": "Claude Opus 4.6",
    "kimik26": "Kimi K2.6",
    "gpt54_temp0_top_p1_seed12345": "GPT-5.4",
    "gpt_5_5_litellm_temp0_top_p1_seed12345": "GPT-5.5",
    "gemini_3_1_flash_image_preview_temp0_top_p1_seed12345": "Gemini 3.1 Flash",
    "gemini_3_pro_image_preview_temp0_top_p1_seed12345": "Gemini 3 Pro",
    "qwen3_5_plus_temp0_top_p1_seed12345": "Qwen 3.5 Plus",
    "qwen3_6_plus_temp0_top_p1_seed12345": "Qwen 3.6 Plus",
    "claude_haiku_4_5_litellm_temp0_top_p1_seed12345": "Claude Haiku 4.5",
    "claude_sonnet_4_6_litellm_temp0_top_p1_seed12345": "Claude Sonnet 4.6",
    "claude_opus_4_6_aime_responses_temp0_top_p1_seed12345": "Claude Opus 4.6",
    "kimik2_6_temp0_top_p1_seed12345": "Kimi K2.6",
}

COLORS = {
    "clean": "#4C78A8",
    "official": "#E4572E",
    "both_success": "#72B7B2",
    "misleading": "#F28E2B",
    "regression": "#B279A2",
    "both_failed": "#D0D0D0",
    "grid": "#E8E8E8",
    "text": "#222222",
}


def read_jsonl(path: Path) -> list[dict]:
    with path.open() as f:
        return [json.loads(line) for line in f if line.strip()]


def save(fig: plt.Figure, name: str) -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    for ext in ("pdf", "png"):
        fig.savefig(FIG_DIR / f"{name}.{ext}", bbox_inches="tight", dpi=300)
    plt.close(fig)


def style_axes(ax: plt.Axes) -> None:
    ax.grid(axis="x", color=COLORS["grid"], linewidth=0.8)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#BBBBBB")
    ax.spines["bottom"].set_color("#BBBBBB")
    ax.tick_params(colors=COLORS["text"], labelsize=9)


def paired_model_metrics(rows: list[dict]) -> list[dict]:
    metrics = []
    for key in PAIR_MODEL_ORDER:
        model_rows = [r for r in rows if r["model_key"] == key]
        n = len(model_rows)
        clean = sum(r["clean_outcome"] == "success" for r in model_rows) / n
        official = sum(r["official_outcome"] == "success" for r in model_rows) / n
        counts = Counter(r["pair_category"] for r in model_rows)
        metrics.append(
            {
                "key": key,
                "name": MODEL_NAME[key],
                "n": n,
                "clean": clean,
                "official": official,
                "gap": clean - official,
                "both_success": counts["official_success_clean_success"] / n,
                "misleading": counts["official_misleading_clean_success"] / n,
                "regression": counts["clean_regression"] / n,
                "both_failed": counts["both_failed"] / n,
            }
        )
    return metrics


def trajectory_metrics(rows: list[dict]) -> list[dict]:
    metrics = []
    for key in STEP_MODEL_ORDER:
        model_rows = [r for r in rows if r["model_slug"] == key]
        n = len(model_rows)
        metrics.append(
            {
                "key": key,
                "name": MODEL_NAME[key],
                "avg_step_delta": sum(r["step_delta"] for r in model_rows) / n,
                "more_steps": sum(r["official_more_steps_flag"] for r in model_rows),
                "avg_du_delta": sum(
                    r["decision_uncertainty_delta"] for r in model_rows
                )
                / n,
                "more_du": sum(
                    r["official_more_decision_uncertain_flag"] for r in model_rows
                ),
            }
        )
    return metrics


def figure5_accuracy_drop(metrics: list[dict]) -> None:
    data = sorted(metrics, key=lambda x: x["gap"], reverse=True)
    y = np.arange(len(data))
    fig, ax = plt.subplots(figsize=(3.35, 3.35))

    for i, item in enumerate(data):
        ax.plot(
            [item["official"] * 100, item["clean"] * 100],
            [i, i],
            color="#C9C9C9",
            linewidth=2,
            zorder=1,
        )
    ax.scatter(
        [d["official"] * 100 for d in data],
        y,
        s=52,
        color=COLORS["official"],
        label="Official misleading",
        zorder=3,
    )
    ax.scatter(
        [d["clean"] * 100 for d in data],
        y,
        s=52,
        color=COLORS["clean"],
        label="Clean",
        zorder=3,
    )
    for i, item in enumerate(data):
        ax.text(
            item["clean"] * 100 + 1.2,
            i,
            f"{item['gap'] * 100:.1f}",
            va="center",
            fontsize=6.5,
            color="#555555",
        )

    ax.set_yticks(y)
    ax.set_yticklabels([d["name"] for d in data], fontsize=6.5)
    ax.invert_yaxis()
    ax.set_xlim(20, 94)
    ax.set_xlabel("Task success rate (%)", fontsize=8)
    ax.legend(loc="lower right", frameon=True, fontsize=6.5)
    style_axes(ax)
    ax.tick_params(axis="x", labelsize=7)
    fig.tight_layout(pad=0.25)
    save(fig, "figure5_paired_accuracy_drop")


def figure6_outcome_composition(metrics: list[dict]) -> None:
    totals = {
        "both_success": sum(d["both_success"] * d["n"] for d in metrics),
        "misleading": sum(d["misleading"] * d["n"] for d in metrics),
        "regression": sum(d["regression"] * d["n"] for d in metrics),
        "both_failed": sum(d["both_failed"] * d["n"] for d in metrics),
    }
    labels = ["Misleading-induced\nfailure", "Clean\nregression"]
    counts = [totals["misleading"], totals["regression"]]
    vals = [c / 1400 * 100 for c in counts]
    fig, ax = plt.subplots(figsize=(3.35, 1.65))
    y = np.arange(len(vals))
    ax.barh(y, vals, color=[COLORS["misleading"], COLORS["regression"]], height=0.48)
    for i, (val, count) in enumerate(zip(vals, counts)):
        ax.text(
            val + 1.0,
            i,
            f"{int(count)}/1400\n({val:.1f}%)",
            va="center",
            fontsize=7,
            color="#444444",
        )
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=7.5)
    ax.invert_yaxis()
    ax.set_xlim(0, 45)
    ax.set_xlabel("Paired outcome rate (%)", fontsize=8)
    style_axes(ax)
    ax.tick_params(axis="x", labelsize=7)
    fig.tight_layout(pad=0.25)
    save(fig, "figure6_pair_outcome_composition")


def figure7_execution_instability(metrics: list[dict]) -> None:
    n = sum(d.get("n", 140) for d in metrics)
    avg_step_delta = sum(d["avg_step_delta"] * 140 for d in metrics) / n
    avg_du_delta = sum(d["avg_du_delta"] * 140 for d in metrics) / n
    more_steps = sum(d["more_steps"] for d in metrics)
    more_du = sum(d["more_du"] for d in metrics)
    fig = plt.figure(figsize=(3.35, 3.25))
    gs = fig.add_gridspec(2, 1, height_ratios=[1.32, 1.0], hspace=0.32)

    motif_ax = fig.add_subplot(gs[0])
    motif_ax.set_xlim(0, 1)
    motif_ax.set_ylim(0, 1)
    motif_ax.axis("off")

    def draw_trace(
        y: float,
        row_label: str,
        steps: list[tuple[float, str, str]],
        arrow_color: str,
    ) -> None:
        motif_ax.text(
            0.015,
            y,
            row_label,
            va="center",
            ha="left",
            fontsize=6.8,
            fontweight="bold",
            color=COLORS["text"],
        )
        for i, (x_pos, step, color_key) in enumerate(steps):
            edge = {
                "page": COLORS["clean"],
                "select": COLORS["official"],
                "submit": "#59A14F",
            }[color_key]
            face = {
                "page": "#F2F7FC",
                "select": "#FFF4EA",
                "submit": "#F2FAF1",
            }[color_key]
            motif_ax.text(
                x_pos,
                y,
                step,
                va="center",
                ha="center",
                fontsize=5.7,
                color="#222222",
                bbox={
                    "boxstyle": "round,pad=0.20,rounding_size=0.08",
                    "facecolor": face,
                    "edgecolor": edge,
                    "linewidth": 0.9,
                },
            )
            if i < len(steps) - 1:
                next_x = steps[i + 1][0]
                motif_ax.annotate(
                    "",
                    xy=(next_x - 0.035, y),
                    xytext=(x_pos + 0.035, y),
                    arrowprops={
                        "arrowstyle": "->",
                        "color": arrow_color,
                        "linewidth": 0.75,
                        "shrinkA": 0,
                        "shrinkB": 0,
                    },
                )

    clean_steps = [
        (0.28, "Dash", "page"),
        (0.49, "Form", "page"),
        (0.69, "A", "select"),
        (0.90, "Submit", "submit"),
    ]
    misleading_steps = [
        (0.25, "Dash", "page"),
        (0.37, "Form", "page"),
        (0.49, "A", "select"),
        (0.60, "B", "select"),
        (0.71, "A", "select"),
        (0.83, "Dash", "page"),
        (0.95, "Form", "page"),
    ]
    draw_trace(0.73, "Clean", clean_steps, "#9DB8D5")
    draw_trace(0.38, "Mislead", misleading_steps, "#E79B73")

    motif_ax.plot([0.47, 0.73], [0.56, 0.56], color=COLORS["official"], linewidth=0.9)
    motif_ax.plot([0.47, 0.47], [0.53, 0.56], color=COLORS["official"], linewidth=0.9)
    motif_ax.plot([0.73, 0.73], [0.53, 0.56], color=COLORS["official"], linewidth=0.9)
    motif_ax.text(
        0.60,
        0.59,
        "option switching",
        ha="center",
        va="bottom",
        fontsize=5.8,
        color=COLORS["official"],
    )
    motif_ax.plot([0.81, 0.97], [0.20, 0.20], color=COLORS["clean"], linewidth=0.9)
    motif_ax.plot([0.81, 0.81], [0.20, 0.23], color=COLORS["clean"], linewidth=0.9)
    motif_ax.plot([0.97, 0.97], [0.20, 0.23], color=COLORS["clean"], linewidth=0.9)
    motif_ax.text(
        0.89,
        0.13,
        "page revisit",
        ha="center",
        va="bottom",
        fontsize=5.8,
        color=COLORS["clean"],
    )
    motif_ax.text(
        0.985,
        0.03,
        "Dash = dashboard; A/B = candidate actions",
        ha="right",
        va="bottom",
        fontsize=5.3,
        color="#666666",
    )

    ax = fig.add_subplot(gs[1])
    labels = ["Step\nInflation", "Decision\nInstability"]
    vals = [avg_step_delta, avg_du_delta]
    counts = [more_steps, more_du]
    x = np.arange(len(vals))
    ax.bar(x, vals, color=[COLORS["official"], COLORS["misleading"]], width=0.48)
    for i, (val, count) in enumerate(zip(vals, counts)):
        ax.text(
            i,
            val + 0.045,
            f"+{val:.2f}\n{count}/1400",
            ha="center",
            va="bottom",
            fontsize=6.8,
            color="#444444",
        )
    ax.axhline(0, color="#999999", linewidth=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=7.4)
    ax.set_ylabel("Average paired delta", fontsize=8)
    ax.set_ylim(0, 0.86)
    ax.grid(axis="y", color=COLORS["grid"], linewidth=0.8)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#BBBBBB")
    ax.spines["bottom"].set_color("#BBBBBB")
    ax.tick_params(axis="y", labelsize=7)
    fig.subplots_adjust(left=0.13, right=0.98, top=0.98, bottom=0.12, hspace=0.44)
    label_x = motif_ax.get_position().x0
    for label, panel_ax in (("(a)", motif_ax), ("(b)", ax)):
        pos = panel_ax.get_position()
        fig.text(
            label_x,
            pos.y1 + 0.006,
            label,
            ha="left",
            va="bottom",
            fontsize=8,
            fontweight="bold",
            color=COLORS["text"],
        )
    save(fig, "figure7_execution_instability")


def main() -> None:
    pair_rows = read_jsonl(PAIR_RESULTS)
    step_rows = read_jsonl(STEP_RESULTS)
    pair_metrics = paired_model_metrics(pair_rows)
    step_metrics = trajectory_metrics(step_rows)
    figure5_accuracy_drop(pair_metrics)
    figure6_outcome_composition(pair_metrics)
    figure7_execution_instability(step_metrics)
    print(f"Wrote figures to {FIG_DIR}")


if __name__ == "__main__":
    main()
