#!/usr/bin/env python3
"""Build clean-pair chart assets for the official 140-task benchmark."""

from __future__ import annotations

import csv
import html
import http.server
import json
import math
import re
import shutil
import socketserver
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from playwright.sync_api import sync_playwright


REPO_ROOT = Path(__file__).resolve().parents[2]
OFFICIAL_DIR = REPO_ROOT / "web_agent_benchmark" / "official_benchmark_v1"
OUT_DIR = REPO_ROOT / "clean_datasets"
MCQA_DATASET = REPO_ROOT / "baseline" / "MisleadingChartQA-main" / "dataset"

SCENARIO_TASK_FILES = [
    ("public39", "public39_tasks.jsonl"),
    ("business47", "business47_tasks.jsonl"),
    ("environment35", "environment35_tasks.jsonl"),
    ("health19", "health19_tasks.jsonl"),
]

BAD_NUMERIC_TOKENS = {
    "adjust",
    "adjusted",
    "scale",
    "scaled",
    "exponent",
    "visual",
    "height",
    "width",
    "radius",
    "size",
    "color",
}

STATE_TILE_POSITIONS = {
    "AK": (0, 0),
    "ME": (11, 0),
    "VT": (10, 1),
    "NH": (11, 1),
    "WA": (1, 2),
    "ID": (2, 2),
    "MT": (3, 2),
    "ND": (4, 2),
    "MN": (5, 2),
    "IL": (6, 2),
    "WI": (7, 2),
    "MI": (8, 2),
    "NY": (9, 2),
    "MA": (10, 2),
    "OR": (1, 3),
    "NV": (2, 3),
    "WY": (3, 3),
    "SD": (4, 3),
    "IA": (5, 3),
    "IN": (6, 3),
    "OH": (7, 3),
    "PA": (8, 3),
    "NJ": (9, 3),
    "CT": (10, 3),
    "RI": (11, 3),
    "CA": (1, 4),
    "UT": (2, 4),
    "CO": (3, 4),
    "NE": (4, 4),
    "MO": (5, 4),
    "KY": (6, 4),
    "WV": (7, 4),
    "VA": (8, 4),
    "MD": (9, 4),
    "DE": (10, 4),
    "AZ": (2, 5),
    "NM": (3, 5),
    "KS": (4, 5),
    "AR": (5, 5),
    "TN": (6, 5),
    "NC": (7, 5),
    "SC": (8, 5),
    "DC": (9, 5),
    "OK": (4, 6),
    "LA": (5, 6),
    "MS": (6, 6),
    "AL": (7, 6),
    "GA": (8, 6),
    "HI": (0, 7),
    "TX": (4, 7),
    "FL": (9, 7),
}


def safe_name(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    value = re.sub(r"_+", "_", value).strip("._")
    return value[:120] or "item"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def prepare_output() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name in ["tasks", "data"]:
        target = OUT_DIR / name
        if target.exists():
            shutil.rmtree(target)
    for name in ["index.html", "manifest.json", "manifest.jsonl", "README.md"]:
        target = OUT_DIR / name
        if target.exists():
            target.unlink()


def copy_official_reference_files() -> None:
    official_out = OUT_DIR / "data" / "official_benchmark_v1"
    official_out.mkdir(parents=True, exist_ok=True)
    for path in sorted(OFFICIAL_DIR.iterdir()):
        if path.is_file() and path.suffix in {".json", ".jsonl", ".md"}:
            shutil.copy2(path, official_out / path.name)


def rel(path: Path | None) -> str | None:
    if not path:
        return None
    try:
        return str(path.relative_to(OUT_DIR))
    except ValueError:
        return str(path)


def copy_file(src: Path | None, dest: Path | None) -> str | None:
    if not src or not dest or not src.exists():
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return rel(dest)


def resolve_mcqa_html(task: dict[str, Any]) -> Path | None:
    chart = task.get("chart_asset") or {}
    html_path = chart.get("html_path")
    if html_path and Path(html_path).exists():
        return Path(html_path)
    case_id = task.get("case_id")
    if case_id:
        candidate = MCQA_DATASET / "code" / f"{case_id}.html"
        if candidate.exists():
            return candidate
    return None


def is_visdeception(task: dict[str, Any]) -> bool:
    figure = ((task.get("chart_asset") or {}).get("figure_path") or "")
    return "/visDeception-main/" in figure


def is_mcqa_series(task: dict[str, Any]) -> bool:
    chart = task.get("chart_asset") or {}
    paths = " ".join(str(chart.get(key) or "") for key in ["figure_path", "csv_path", "html_path"])
    return task.get("source_dataset") == "MisleadingChartQA" or "/MisleadingChartQA-main/" in paths


def paired_visdeception_clean_path(misleading_path: Path) -> Path | None:
    stem = misleading_path.stem
    candidates: list[Path] = []
    if stem.endswith("_Aggressive"):
        candidates.append(misleading_path.with_name(stem[: -len("_Aggressive")] + "_Control" + misleading_path.suffix))
    if stem.endswith("_dual"):
        candidates.append(misleading_path.with_name(stem[: -len("_dual")] + "_regular" + misleading_path.suffix))
    if "_dual" in stem:
        candidates.append(misleading_path.with_name(stem.replace("_dual", "_regular") + misleading_path.suffix))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def read_csv_rows(path: Path | None) -> list[dict[str, str]]:
    if not path or not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def clean_dataframe(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = df.dropna(how="all")
    return df


def true_numeric_columns(df: pd.DataFrame) -> list[str]:
    numeric: list[str] = []
    for column in df.columns:
        series = pd.to_numeric(df[column], errors="coerce")
        if series.notna().sum() == 0:
            continue
        lower = column.lower()
        if any(token in lower for token in BAD_NUMERIC_TOKENS):
            continue
        numeric.append(column)
    non_identifier = [col for col in numeric if col.lower() not in {"id", "state", "fips"}]
    if non_identifier:
        numeric = non_identifier
    if numeric:
        return numeric
    fallback: list[str] = []
    for column in df.columns:
        series = pd.to_numeric(df[column], errors="coerce")
        if series.notna().sum() > 0 and "color" not in column.lower():
            fallback.append(column)
    return fallback


def categorical_columns(df: pd.DataFrame) -> list[str]:
    cols: list[str] = []
    for column in df.columns:
        lower = column.lower()
        if "color" in lower:
            continue
        numeric = pd.to_numeric(df[column], errors="coerce")
        if numeric.notna().sum() < max(1, len(df) * 0.6):
            cols.append(column)
    return cols


def first_existing(cols: list[str], preferences: list[str]) -> str | None:
    by_lower = {col.lower(): col for col in cols}
    for pref in preferences:
        if pref in by_lower:
            return by_lower[pref]
    for col in cols:
        lower = col.lower()
        if any(pref in lower for pref in preferences):
            return col
    return None


def choose_x_column(df: pd.DataFrame, y_cols: list[str], plot_type: str) -> str | None:
    cols = [col for col in df.columns if col not in y_cols]
    preferred = first_existing(cols, ["year", "date", "month", "quarter", "product", "brand", "browser", "preference", "mode", "state"])
    if preferred:
        return preferred
    cats = [col for col in categorical_columns(df) if col not in y_cols]
    if cats:
        return cats[0]
    if plot_type == "scatter_plot":
        return None
    return cols[0] if cols else None


def choose_y_columns(df: pd.DataFrame, plot_type: str) -> list[str]:
    numeric = true_numeric_columns(df)
    if not numeric:
        return []
    if plot_type in {"line_chart", "stacked_bar_chart"}:
        if plot_type == "line_chart":
            ignored = {"year"}
            filtered = [col for col in numeric if col.lower() not in ignored]
            return filtered or numeric[-1:]
        return numeric
    if plot_type == "scatter_plot":
        return numeric[:2] if len(numeric) >= 2 else numeric[:1]
    return numeric[:1]


def chart_title(task: dict[str, Any]) -> str:
    chart = task.get("chart_asset") or {}
    source_html = resolve_mcqa_html(task) if is_mcqa_series(task) else None
    if source_html and source_html.exists():
        text = source_html.read_text(encoding="utf-8", errors="ignore")
        for pattern in [r"<h1[^>]*>(.*?)</h1>", r"<h2[^>]*>(.*?)</h2>", r"<title[^>]*>(.*?)</title>"]:
            match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
            if match:
                title = re.sub(r"<[^>]+>", "", match.group(1)).strip()
                if title:
                    return html.unescape(title)
    return (
        task.get("page_title")
        or chart.get("html_title")
        or (task.get("shell_page_design") or {}).get("page_title")
        or task.get("case_id")
        or task.get("official_slug")
        or "Clean Chart"
    )


def configure_axes(ax: plt.Axes, title: str) -> None:
    ax.set_title(title, fontsize=16, pad=16)
    ax.grid(True, axis="y", color="#d8dde6", linewidth=0.8, alpha=0.8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def save_no_data_chart(task: dict[str, Any], dest: Path, message: str) -> None:
    fig, ax = plt.subplots(figsize=(10, 7.5), dpi=140)
    ax.axis("off")
    ax.text(0.5, 0.55, chart_title(task), ha="center", va="center", fontsize=18, weight="bold")
    ax.text(0.5, 0.45, message, ha="center", va="center", fontsize=12, wrap=True)
    fig.tight_layout()
    fig.savefig(dest, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def render_clean_chart(task: dict[str, Any], csv_path: Path, dest: Path) -> dict[str, Any]:
    df = clean_dataframe(csv_path)
    plot_type = task.get("plot_type") or ""
    misleader = task.get("misleader_type") or ""
    title = chart_title(task)
    render_info: dict[str, Any] = {"renderer": "matplotlib", "plot_type": plot_type, "misleader_type": misleader}
    if df.empty:
        save_no_data_chart(task, dest, "No CSV rows were available.")
        render_info["note"] = "empty_csv"
        return render_info

    if plot_type == "choropleth_map":
        raise RuntimeError("Choropleth maps should be rendered from source-like D3 HTML.")
    if plot_type == "pie_chart":
        render_pie(task, df, dest)
        render_info["cleaning_rule"] = "pie_slices_use_true_value_column"
        return render_info
    if plot_type == "scatter_plot":
        render_scatter(task, df, dest)
        render_info["cleaning_rule"] = "positions_use_true_data_columns"
        return render_info
    if plot_type == "line_chart":
        render_line(task, df, dest)
        render_info["cleaning_rule"] = "linear_axis_full_available_series"
        return render_info
    if plot_type == "stacked_bar_chart":
        render_stacked_or_grouped(task, df, dest)
        render_info["cleaning_rule"] = "zero_baseline_and_explicit_series_values"
        return render_info
    render_bar(task, df, dest)
    render_info["cleaning_rule"] = "bar_lengths_use_true_value_column_with_zero_baseline"
    return render_info


def render_bar(task: dict[str, Any], df: pd.DataFrame, dest: Path) -> None:
    y_cols = choose_y_columns(df, "bar_chart")
    if not y_cols:
        save_no_data_chart(task, dest, "No numeric value column was available.")
        return
    x_col = choose_x_column(df, y_cols, "bar_chart") or df.index.name or "index"
    values = pd.to_numeric(df[y_cols[0]], errors="coerce").fillna(0)
    labels = df[x_col].astype(str).tolist() if x_col in df.columns else [str(i + 1) for i in range(len(df))]
    order = np.arange(len(df))
    fig, ax = plt.subplots(figsize=(10, 7.5), dpi=140)
    ax.bar(order, values, color="#2f7f8f")
    ax.set_xticks(order, labels, rotation=35, ha="right")
    ax.set_ylabel(y_cols[0])
    ax.set_ylim(bottom=0)
    configure_axes(ax, chart_title(task))
    fig.tight_layout()
    fig.savefig(dest, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def render_stacked_or_grouped(task: dict[str, Any], df: pd.DataFrame, dest: Path) -> None:
    y_cols = choose_y_columns(df, "stacked_bar_chart")
    if not y_cols:
        render_bar(task, df, dest)
        return
    x_col = choose_x_column(df, y_cols, "stacked_bar_chart")
    labels = df[x_col].astype(str).tolist() if x_col in df.columns else [str(i + 1) for i in range(len(df))]
    values = df[y_cols].apply(pd.to_numeric, errors="coerce").fillna(0)
    fig, ax = plt.subplots(figsize=(10.5, 7.5), dpi=140)
    x = np.arange(len(df))
    if task.get("misleader_type") == "misuse_of_cumulative_relationship":
        width = min(0.8 / max(len(y_cols), 1), 0.25)
        offsets = (np.arange(len(y_cols)) - (len(y_cols) - 1) / 2) * width
        for idx, col in enumerate(y_cols):
            ax.bar(x + offsets[idx], values[col], width=width, label=col)
    else:
        bottom = np.zeros(len(df))
        for col in y_cols:
            ax.bar(x, values[col], bottom=bottom, label=col)
            bottom += values[col].to_numpy()
    ax.set_xticks(x, labels, rotation=35, ha="right")
    ax.set_ylim(bottom=0)
    ax.legend(loc="best", fontsize=9)
    ax.set_ylabel("Value")
    configure_axes(ax, chart_title(task))
    fig.tight_layout()
    fig.savefig(dest, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def render_line(task: dict[str, Any], df: pd.DataFrame, dest: Path) -> None:
    y_cols = choose_y_columns(df, "line_chart")
    if not y_cols:
        save_no_data_chart(task, dest, "No numeric value column was available.")
        return
    x_col = choose_x_column(df, y_cols, "line_chart")
    work = df.copy()
    if x_col and x_col in work.columns:
        x_values = work[x_col]
        sort_values = pd.to_numeric(x_values, errors="coerce")
        if sort_values.notna().sum() == len(work):
            work = work.assign(__sort=sort_values).sort_values("__sort")
            x_values = work[x_col]
    else:
        x_values = pd.Series(range(1, len(work) + 1))
    fig, ax = plt.subplots(figsize=(10, 7.5), dpi=140)
    for col in y_cols:
        y = pd.to_numeric(work[col], errors="coerce")
        ax.plot(x_values.astype(str), y, marker="o", linewidth=2.2, label=col)
    if len(y_cols) > 1:
        ax.legend(loc="best", fontsize=9)
    ax.set_xlabel(x_col or "Observation")
    ax.set_ylabel(", ".join(y_cols))
    ax.tick_params(axis="x", rotation=35)
    configure_axes(ax, chart_title(task))
    fig.tight_layout()
    fig.savefig(dest, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def render_scatter(task: dict[str, Any], df: pd.DataFrame, dest: Path) -> None:
    y_cols = choose_y_columns(df, "scatter_plot")
    fig, ax = plt.subplots(figsize=(10, 7.5), dpi=140)
    if len(y_cols) >= 2:
        x = pd.to_numeric(df[y_cols[0]], errors="coerce")
        y = pd.to_numeric(df[y_cols[1]], errors="coerce")
        ax.scatter(x, y, s=95, color="#2f7f8f", alpha=0.9)
        label_col = choose_x_column(df, y_cols, "scatter_plot")
        if label_col:
            for _, row in df.iterrows():
                xv = pd.to_numeric(pd.Series([row[y_cols[0]]]), errors="coerce").iloc[0]
                yv = pd.to_numeric(pd.Series([row[y_cols[1]]]), errors="coerce").iloc[0]
                if pd.notna(xv) and pd.notna(yv):
                    ax.annotate(str(row[label_col]), (xv, yv), xytext=(5, 5), textcoords="offset points", fontsize=8)
        ax.set_xlabel(y_cols[0])
        ax.set_ylabel(y_cols[1])
    elif len(y_cols) == 1:
        x_col = choose_x_column(df, y_cols, "scatter_plot")
        labels = df[x_col].astype(str).tolist() if x_col in df.columns else [str(i + 1) for i in range(len(df))]
        x = np.arange(len(df))
        y = pd.to_numeric(df[y_cols[0]], errors="coerce")
        ax.scatter(x, y, s=95, color="#2f7f8f", alpha=0.9)
        ax.set_xticks(x, labels, rotation=35, ha="right")
        ax.set_ylabel(y_cols[0])
    else:
        save_no_data_chart(task, dest, "No numeric value column was available.")
        plt.close(fig)
        return
    configure_axes(ax, chart_title(task))
    fig.tight_layout()
    fig.savefig(dest, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def render_pie(task: dict[str, Any], df: pd.DataFrame, dest: Path) -> None:
    y_cols = choose_y_columns(df, "pie_chart")
    if not y_cols:
        save_no_data_chart(task, dest, "No numeric value column was available.")
        return
    cat_cols = categorical_columns(df)
    label_col = cat_cols[0] if cat_cols else df.columns[0]
    values = pd.to_numeric(df[y_cols[0]], errors="coerce").fillna(0)
    labels = df[label_col].astype(str).tolist()
    fig, ax = plt.subplots(figsize=(9.5, 7.5), dpi=140)
    ax.pie(values, labels=labels, autopct="%1.1f%%", startangle=90, counterclock=False)
    ax.set_title(chart_title(task), fontsize=16, pad=16)
    ax.axis("equal")
    fig.tight_layout()
    fig.savefig(dest, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def render_choropleth_source_map(task: dict[str, Any], csv_path: Path, dest: Path, task_dir: Path) -> dict[str, Any]:
    df = clean_dataframe(csv_path)
    numeric_cols = true_numeric_columns(df)
    if not numeric_cols:
        raise ValueError(f"No numeric value column available for choropleth task {task.get('official_slug')}")
    value_col = numeric_cols[0]
    id_col = first_existing(list(df.columns), ["id", "fips", "state"]) or df.columns[0]
    label_col = first_existing(list(df.columns), ["abbr", "state", "State"]) or id_col
    values = pd.to_numeric(df[value_col], errors="coerce")
    value_min = float(values.min())
    value_max = float(values.max())
    if not math.isfinite(value_min) or not math.isfinite(value_max):
        raise ValueError(f"Invalid numeric values for choropleth task {task.get('official_slug')}")
    if value_min == value_max:
        value_min = 0.0
    preserve_original_unmatched_fips = task.get("official_slug") in {f"pub{i:03d}" for i in range(12, 19)}

    title = chart_title(task)
    source_rows = df.to_dict("records")
    source_json = json.dumps(source_rows, ensure_ascii=False)
    clean_note = "Clean choropleth: same US map base; darker color means higher true value."
    clean_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html.escape(title)}</title>
    <script src="https://d3js.org/d3.v6.min.js"></script>
    <script src="https://d3js.org/topojson.v3.min.js"></script>
    <style>
        body {{ margin: 8px; background: #fff; color: #111; }}
        h1 {{ font-family: serif; font-size: 24px; margin: 12px 0 0 0; }}
        .state {{ stroke: #fff; stroke-width: 0.5px; }}
        .legend {{ font-size: 14px; }}
        .state-label {{ text-anchor: middle; font-size: 10px; fill: black; pointer-events: none; }}
        .clean-note {{ font: 13px Arial, sans-serif; fill: #4b5563; }}
    </style>
</head>
<body>
    <h1>{html.escape(title)}</h1>
    <div id="map"></div>
    <script>
        const width = 1000, height = 750;
        const data = {source_json};
        const idColumn = {json.dumps(id_col)};
        const labelColumn = {json.dumps(label_col)};
        const valueColumn = {json.dumps(value_col)};
        const valueMin = {value_min};
        const valueMax = {value_max};
        const preserveOriginalUnmatchedFips = {json.dumps(preserve_original_unmatched_fips)};
        const svg = d3.select("#map").append("svg").attr("width", width).attr("height", height);
        const path = d3.geoPath();
        const color = d3.scaleSequential(d3.interpolateYlOrRd).domain([valueMin, valueMax]);

        d3.json("https://d3js.org/us-10m.v1.json").then(us => {{
            const valueById = new Map();
            const labelById = new Map();
            data.forEach(d => {{
                const rawId = String(d[idColumn]);
                const paddedId = /^\\d+$/.test(rawId) ? rawId.padStart(2, "0") : rawId;
                const value = +d[valueColumn];
                const label = String(d[labelColumn]);
                const keys = preserveOriginalUnmatchedFips ? [rawId] : [rawId, paddedId];
                keys.forEach(key => {{
                    valueById.set(key, value);
                    labelById.set(key, label);
                }});
            }});
            const states = topojson.feature(us, us.objects.states).features;

            svg.append("g")
                .selectAll("path")
                .data(states)
                .enter().append("path")
                .attr("class", "state")
                .attr("fill", d => {{
                    const value = valueById.get(String(d.id));
                    return value !== undefined && Number.isFinite(value) ? color(value) : "#ddd";
                }})
                .attr("d", path);

            svg.selectAll(".state-label")
                .data(states)
                .enter().append("text")
                .attr("class", "state-label")
                .attr("transform", d => "translate(" + path.centroid(d) + ")")
                .attr("dy", ".35em")
                .text(d => labelById.get(String(d.id)) || "");

            const legend = svg.append("g").attr("class", "legend").attr("transform", "translate(900,300)");
            const legendValues = d3.range(0, 101).map(i => valueMin + (valueMax - valueMin) * i / 100);
            const legendScale = d3.scaleLinear().domain([valueMax, valueMin]).range([0, 200]);
            const legendAxis = d3.axisRight(legendScale).ticks(5);

            legend.selectAll("rect")
                .data(legendValues)
                .enter().append("rect")
                .attr("x", 0)
                .attr("y", d => legendScale(d))
                .attr("width", 20)
                .attr("height", 2)
                .attr("fill", d => color(d));

            legend.append("g").attr("transform", "translate(20,0)").call(legendAxis);
            legend.append("text").attr("x", -10).attr("y", 0).attr("text-anchor", "end").text("High");
            legend.append("text").attr("x", -10).attr("y", 200).attr("text-anchor", "end").text("Low");
            svg.append("text").attr("x", 0).attr("y", 735).attr("class", "clean-note").text({json.dumps(clean_note)});
        }});
    </script>
</body>
</html>"""
    clean_html_path = task_dir / "clean_source.html"
    clean_html_path.write_text(clean_html, encoding="utf-8")
    screenshot_html(clean_html_path, dest)
    return {
        "renderer": "d3_playwright",
        "plot_type": task.get("plot_type"),
        "misleader_type": task.get("misleader_type"),
        "cleaning_rule": "source-like_us_choropleth_true_value_color_domain",
        "clean_source_html": rel(clean_html_path),
        "choropleth_value_column": value_col,
        "choropleth_id_column": id_col,
        "choropleth_label_column": label_col,
        "preserve_original_unmatched_fips_gray": preserve_original_unmatched_fips,
    }


def render_stacked_bar_source_chart(task: dict[str, Any], csv_path: Path, dest: Path, task_dir: Path) -> dict[str, Any]:
    df = clean_dataframe(csv_path)
    y_cols = choose_y_columns(df, "stacked_bar_chart")
    if not y_cols:
        raise ValueError(f"No numeric value columns available for stacked bar task {task.get('official_slug')}")
    x_col = choose_x_column(df, y_cols, "stacked_bar_chart") or df.columns[0]
    title = chart_title(task)
    source_json = json.dumps(df.to_dict("records"), ensure_ascii=False)
    keys_json = json.dumps(y_cols, ensure_ascii=False)
    clean_note = "Clean stacked bar: same layout and colors; y-axis starts at 0 so bar heights show the full true totals."
    clean_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(title)}</title>
  <script src="https://d3js.org/d3.v6.min.js"></script>
  <style>
    #chart {{
      width: 1000px;
      height: 750px;
      margin: 60px auto;
    }}
    .axis path, .axis line {{ stroke: #000; }}
    .label {{ font-size: 12px; font-weight: bold; fill: white; text-anchor: middle; }}
    .legend text {{ font-size: 12px; }}
    .axis-label {{ font-size: 14px; font-weight: bold; text-anchor: middle; }}
    .clean-note {{ font: 13px Arial, sans-serif; fill: #4b5563; }}
  </style>
</head>
<body>
  <h1>{html.escape(title)}</h1>
  <div id="chart"></div>
  <script>
    const margin = {{top: 40, right: 150, bottom: 60, left: 60}};
    const width = 1000 - margin.left - margin.right;
    const height = 750 - margin.top - margin.bottom;

    const svg = d3.select("#chart").append("svg")
      .attr("width", width + margin.left + margin.right)
      .attr("height", height + margin.top + margin.bottom);

    const g = svg.append("g").attr("transform", `translate(${{margin.left}},${{margin.top}})`);

    const data = {source_json};
    const xColumn = {json.dumps(x_col)};
    const keys = {keys_json};
    const color = d3.scaleOrdinal()
      .domain(keys)
      .range(["#1f77b4", "#2ca02c", "#ff7f0e", "#9467bd"]);

    data.forEach(d => {{
      keys.forEach(k => d[k] = +d[k]);
    }});

    const stackedData = d3.stack().keys(keys)(data);

    const x = d3.scaleBand()
      .domain(data.map(d => d[xColumn]))
      .range([0, width])
      .padding(0.3);

    const y = d3.scaleLinear()
      .domain([0, d3.max(stackedData.flat(), d => d[1])])
      .nice()
      .range([height, 0]);

    g.selectAll(".layer")
      .data(stackedData)
      .enter().append("g")
      .attr("fill", d => color(d.key))
      .selectAll("rect")
      .data(d => d)
      .enter().append("rect")
      .attr("x", d => x(d.data[xColumn]))
      .attr("y", d => y(d[1]))
      .attr("height", d => y(d[0]) - y(d[1]))
      .attr("width", x.bandwidth());

    g.append("g")
      .attr("class", "axis")
      .attr("transform", `translate(0,${{height}})`)
      .call(d3.axisBottom(x));

    g.append("g")
      .attr("class", "axis")
      .call(d3.axisLeft(y).tickFormat(d3.format(",.0f")));

    g.append("text")
      .attr("class", "axis-label")
      .attr("x", width / 2 + 10)
      .attr("y", height + margin.top - 10)
      .text({json.dumps(x_col.title() if x_col else "Date")});

    g.append("text")
      .attr("class", "axis-label")
      .attr("transform", "rotate(-90)")
      .attr("x", -height / 2 - 50)
      .attr("y", margin.left - 110)
      .text("Number of Visitors");

    const legend = svg.append("g")
      .attr("transform", `translate(${{width + margin.left + 10}},${{margin.top + 20}})`);

    legend.selectAll("rect")
      .data(color.domain())
      .enter().append("rect")
      .attr("x", 0)
      .attr("y", (d, i) => i * 20)
      .attr("width", 18)
      .attr("height", 18)
      .style("fill", color);

    legend.selectAll("text")
      .data(color.domain())
      .enter().append("text")
      .attr("x", 24)
      .attr("y", (d, i) => i * 20 + 14)
      .attr("dy", ".35em")
      .style("font-size", "14px")
      .text(d => d);

    svg.append("text")
      .attr("x", margin.left)
      .attr("y", height + margin.top + margin.bottom - 8)
      .attr("class", "clean-note")
      .text({json.dumps(clean_note)});
  </script>
</body>
</html>"""
    clean_html_path = task_dir / "clean_source.html"
    clean_html_path.write_text(clean_html, encoding="utf-8")
    screenshot_html(clean_html_path, dest)
    return {
        "renderer": "d3_playwright",
        "plot_type": task.get("plot_type"),
        "misleader_type": task.get("misleader_type"),
        "cleaning_rule": "source-like_stacked_bar_zero_baseline_true_totals",
        "clean_source_html": rel(clean_html_path),
        "stacked_bar_x_column": x_col,
        "stacked_bar_value_columns": y_cols,
    }


def render_pub010_line_source_chart(task: dict[str, Any], csv_path: Path, dest: Path, task_dir: Path) -> dict[str, Any]:
    df = clean_dataframe(csv_path)
    if "year" not in df.columns or "tourists" not in df.columns:
        raise ValueError("pub010 expected year and tourists columns")
    data = [
        {"year": str(row["year"]), "tourists": float(row["tourists"])}
        for _, row in df.iterrows()
    ]
    y_max = max(item["tourists"] for item in data) * 1.1
    title = "Increasing Number of New Tourists in Town Z from 1880 to 1891"
    source_json = json.dumps(data, ensure_ascii=False)
    clean_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Line Chart</title>
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <style>
        #chart {{ width: 1000px; height: 750px; margin: 60px auto; }}
        .line {{ fill: none; stroke: steelblue; stroke-width: 3px; }}
        .axis path, .axis line {{ stroke: black; }}
    </style>
</head>
<body>
    <h1>{html.escape(title)}</h1>
    <div id="chart"></div>
    <script>
        const margin = {{top: 40, right: 20, bottom: 40, left: 60}};
        const width = 1000 - margin.left - margin.right;
        const height = 750 - margin.top - margin.bottom;
        const g = d3.select("#chart").append("svg")
            .attr("width", width + margin.left + margin.right)
            .attr("height", height + margin.top + margin.bottom)
            .append("g").attr("transform", `translate(${{margin.left}},${{margin.top}})`);
        const data = {source_json};
        const x = d3.scalePoint().domain(data.map(d => d.year)).range([0, width]);
        const y = d3.scaleLinear().domain([0, {y_max}]).range([height, 0]);
        const line = d3.line().x(d => x(d.year)).y(d => y(d.tourists));
        g.append("g").attr("class", "axis").attr("transform", `translate(0,${{height}})`).call(d3.axisBottom(x));
        g.append("g").attr("class", "axis").call(d3.axisLeft(y));
        g.append("text").attr("x", width/2).attr("y", height + 35).attr("text-anchor", "middle").text("Year");
        g.append("text").attr("transform", "rotate(-90)").attr("x", -height/2).attr("y", -45).attr("text-anchor", "middle").text("Number of Tourists");
        g.append("path").datum(data).attr("class", "line").attr("d", line);
    </script>
</body>
</html>"""
    clean_html_path = task_dir / "clean_source.html"
    clean_html_path.write_text(clean_html, encoding="utf-8")
    screenshot_html(clean_html_path, dest)
    return {
        "renderer": "d3_playwright",
        "plot_type": task.get("plot_type"),
        "misleader_type": task.get("misleader_type"),
        "cleaning_rule": "source-like_line_chart_corrected_increasing_title",
        "clean_source_html": rel(clean_html_path),
        "corrected_title": title,
    }


def render_pub011_bar_source_chart(task: dict[str, Any], csv_path: Path, dest: Path, task_dir: Path) -> dict[str, Any]:
    df = clean_dataframe(csv_path)
    if "month" not in df.columns or "visitors" not in df.columns:
        raise ValueError("pub011 expected month and visitors columns")
    data = [
        {"month": str(row["month"]), "visitors": float(row["visitors"])}
        for _, row in df.iterrows()
    ]
    true_average = sum(item["visitors"] for item in data) / len(data)
    title = chart_title(task)
    source_json = json.dumps(data, ensure_ascii=False)
    clean_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>bar_chart Visualization</title>
    <script src="https://d3js.org/d3.v6.min.js"></script>
    <style>
        #chart {{
            width: 1000px;
            height: 750px;
            margin: 60px auto;
        }}
        .bar {{
            fill: #2ca02c;
        }}
        .avg-line {{
            stroke: orange;
            stroke-dasharray: 4,4;
            stroke-width: 2px;
        }}
        .annotation {{
            font-size: 12px;
            font-weight: bold;
            fill: orange;
        }}
        .axis path, .axis line {{
            stroke: black;
        }}
    </style>
</head>
<body>
    <h1>{html.escape(title)}</h1>
    <div id="chart"></div>
    <script>
        const margin = {{top: 40, right: 20, bottom: 40, left: 60}};
        const width = 1000 - margin.left - margin.right;
        const height = 750 - margin.top - margin.bottom;

        const svg = d3.select("#chart").append("svg")
            .attr("width", width + margin.left + margin.right)
            .attr("height", height + margin.top + margin.bottom);

        const g = svg.append("g").attr("transform", `translate(${{margin.left}},${{margin.top}})`);
        const data = {source_json};
        const trueAverage = {true_average};

        const x = d3.scaleBand().domain(data.map(d => d.month)).range([0, width]).padding(0.3);
        const y = d3.scaleLinear().domain([0, 500]).range([height, 0]);

        g.append("g")
            .attr("class", "axis")
            .attr("transform", `translate(0,${{height}})`)
            .call(d3.axisBottom(x));
        g.append("g").attr("class", "axis").call(d3.axisLeft(y));

        g.append("text")
            .attr("x", width / 2)
            .attr("y", height + 35)
            .attr("text-anchor", "middle")
            .text("Month");

        g.append("text")
            .attr("transform", "rotate(-90)")
            .attr("x", -height / 2)
            .attr("y", -45)
            .attr("text-anchor", "middle")
            .text("Number of Visitors");

        g.selectAll(".bar")
            .data(data)
            .enter().append("rect")
            .attr("class", "bar")
            .attr("x", d => x(d.month))
            .attr("y", d => y(d.visitors))
            .attr("width", x.bandwidth())
            .attr("height", d => height - y(d.visitors));

        g.append("line")
            .attr("class", "avg-line")
            .attr("x1", 0)
            .attr("y1", y(trueAverage))
            .attr("x2", width)
            .attr("y2", y(trueAverage));

        g.append("text")
            .attr("class", "annotation")
            .attr("x", width - 10)
            .attr("y", y(trueAverage) - 10)
            .attr("text-anchor", "end")
            .text("Average");
    </script>
</body>
</html>"""
    clean_html_path = task_dir / "clean_source.html"
    clean_html_path.write_text(clean_html, encoding="utf-8")
    screenshot_html(clean_html_path, dest)
    return {
        "renderer": "d3_playwright",
        "plot_type": task.get("plot_type"),
        "misleader_type": task.get("misleader_type"),
        "cleaning_rule": "source-like_bar_chart_true_average_annotation",
        "clean_source_html": rel(clean_html_path),
        "true_average": true_average,
    }


def source_css_value(task: dict[str, Any], selector: str, property_name: str, fallback: str) -> str:
    text = source_html_text(task)
    pattern = rf"{re.escape(selector)}\s*\{{[^}}]*{re.escape(property_name)}\s*:\s*([^;}}]+)"
    match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
    return match.group(1).strip() if match else fallback


def render_misleading_annotation_bar_source_chart(task: dict[str, Any], csv_path: Path, dest: Path, task_dir: Path) -> dict[str, Any]:
    df = clean_dataframe(csv_path)
    category_col = first_existing(list(df.columns), ["month", "week"]) or df.columns[0]
    value_candidates = [col for col in df.columns if col != category_col]
    value_col = first_existing(value_candidates, ["customers", "sales", "revenue"]) or value_candidates[0]
    data = [
        {"category": str(row[category_col]), "value": float(row[value_col])}
        for _, row in df.iterrows()
    ]
    true_average = sum(item["value"] for item in data) / len(data)
    y_max = source_y_domain_max(task, max(item["value"] for item in data) * 1.15)
    title = chart_title(task)
    x_label = "Week" if category_col.lower() == "week" else "Month"
    y_labels = {
        "customers": "Number of Customers",
        "sales": "Sales ($K)",
        "revenue": "Revenue ($K)",
    }
    y_label = y_labels.get(value_col.lower(), value_col)
    bar_fill = source_css_value(task, ".bar", "fill", "steelblue")
    avg_stroke = source_css_value(task, ".avg-line", "stroke", "black")
    annotation_fill = source_css_value(task, ".annotation", "fill", avg_stroke)
    source_json = json.dumps(data, ensure_ascii=False)
    clean_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html.escape(title)}</title>
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <style>
        #chart {{ width: 1000px; height: 750px; margin: 60px auto; }}
        .bar {{ fill: {bar_fill}; }}
        .avg-line {{ stroke: {avg_stroke}; stroke-dasharray: 4,4; stroke-width: 2px; }}
        .annotation {{ font-size: 12px; font-weight: bold; fill: {annotation_fill}; }}
        .axis path, .axis line {{ stroke: black; }}
    </style>
</head>
<body>
    <h1>{html.escape(title)}</h1>
    <div id="chart"></div>
    <script>
        const margin = {{top: 40, right: 20, bottom: 40, left: 60}};
        const width = 1000 - margin.left - margin.right;
        const height = 750 - margin.top - margin.bottom;
        const svg = d3.select("#chart").append("svg")
            .attr("width", width + margin.left + margin.right)
            .attr("height", height + margin.top + margin.bottom);
        const g = svg.append("g").attr("transform", `translate(${{margin.left}},${{margin.top}})`);
        const data = {source_json};
        const trueAverage = {true_average};

        const x = d3.scaleBand().domain(data.map(d => d.category)).range([0, width]).padding(0.3);
        const y = d3.scaleLinear().domain([0, {y_max}]).range([height, 0]);

        g.append("g").attr("class", "axis").attr("transform", `translate(0,${{height}})`).call(d3.axisBottom(x));
        g.append("g").attr("class", "axis").call(d3.axisLeft(y));
        g.append("text").attr("x", width / 2).attr("y", height + 35).attr("text-anchor", "middle").text("{html.escape(x_label)}");
        g.append("text").attr("transform", "rotate(-90)").attr("x", -height / 2).attr("y", -45).attr("text-anchor", "middle").text("{html.escape(y_label)}");

        g.selectAll(".bar").data(data).enter().append("rect").attr("class", "bar")
            .attr("x", d => x(d.category))
            .attr("y", d => y(d.value))
            .attr("width", x.bandwidth())
            .attr("height", d => height - y(d.value));

        g.append("line").attr("class", "avg-line")
            .attr("x1", 0).attr("y1", y(trueAverage))
            .attr("x2", width).attr("y2", y(trueAverage));
        g.append("text").attr("class", "annotation")
            .attr("x", width - 10).attr("y", y(trueAverage) - 10)
            .attr("text-anchor", "end").text("Average");
    </script>
</body>
</html>"""
    clean_html_path = task_dir / "clean_source.html"
    clean_html_path.write_text(clean_html, encoding="utf-8")
    screenshot_html(clean_html_path, dest)
    return {
        "renderer": "d3_playwright",
        "plot_type": task.get("plot_type"),
        "misleader_type": task.get("misleader_type"),
        "cleaning_rule": "source-like_bar_chart_true_average_annotation",
        "clean_source_html": rel(clean_html_path),
        "true_average": true_average,
        "category_column": category_col,
        "value_column": value_col,
    }


def source_html_text(task: dict[str, Any]) -> str:
    path = resolve_mcqa_html(task)
    if path and path.exists():
        return path.read_text(encoding="utf-8", errors="ignore")
    return ""


def source_y_domain_max(task: dict[str, Any], fallback: float) -> float:
    text = source_html_text(task)
    match = re.search(r"\.domain\(\s*\[\s*0\s*,\s*([0-9.]+)\s*\]\s*\)", text)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            pass
    return fallback


def render_data_visual_disproportion_scatter_source_chart(task: dict[str, Any], csv_path: Path, dest: Path, task_dir: Path) -> dict[str, Any]:
    df = clean_dataframe(csv_path)
    required = {"preference", "mislabeled_value"}
    if not required.issubset(df.columns):
        raise ValueError(f"{task.get('official_slug')} expected preference and mislabeled_value columns")
    data = [
        {"preference": str(row["preference"]), "mislabeled_value": float(row["mislabeled_value"])}
        for _, row in df.iterrows()
    ]
    y_max = max(item["mislabeled_value"] for item in data) + 5
    title = chart_title(task)
    source_json = json.dumps(data, ensure_ascii=False)
    clean_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Product Ratings</title>
  <script src="https://d3js.org/d3.v7.min.js"></script>
  <style>
    #chart {{ width: 1000px; height: 750px; margin: 60px auto; }}
    .axis-label {{ font-size: 14px; font-weight: bold; }}
    .dot {{ fill: steelblue; stroke: black; stroke-width: 1px; }}
  </style>
</head>
<body>
  <h1>{html.escape(title)}</h1>
  <div id="chart"></div>
  <script>
    const margin = {{ top: 40, right: 150, bottom: 50, left: 70 }};
    const width = 1000 - margin.left - margin.right;
    const height = 750 - margin.top - margin.bottom;
    const svg = d3.select("#chart").append("svg")
      .attr("width", width + margin.left + margin.right)
      .attr("height", height + margin.top + margin.bottom)
      .append("g").attr("transform", `translate(${{margin.left}}, ${{margin.top}})`);

    const data = {source_json};
    const categories = data.map(d => d.preference);
    const color = d3.scaleOrdinal().domain(categories).range(d3.schemeCategory10);
    const x = d3.scaleBand().domain(categories).range([0, width]).padding(0.4);
    const y = d3.scaleLinear().domain([0, {y_max}]).range([height, 0]);

    svg.append("g").attr("transform", `translate(0, ${{height}})`).call(d3.axisBottom(x));
    svg.append("g").call(d3.axisLeft(y));
    svg.append("text").attr("class", "axis-label").attr("x", width/2).attr("y", height+40).attr("text-anchor", "middle").text("Category");
    svg.append("text").attr("class", "axis-label").attr("transform", "rotate(-90)").attr("x", -height/2).attr("y", -50).attr("text-anchor", "middle").text("Value");

    svg.selectAll(".dot").data(data).enter().append("circle")
      .attr("class", "dot")
      .attr("cx", d => x(d.preference) + x.bandwidth()/2)
      .attr("cy", d => y(d.mislabeled_value))
      .attr("r", 10)
      .attr("stroke", d => color(d.preference))
      .attr("fill", d => color(d.preference));

    svg.selectAll(".label").data(data).enter().append("text")
      .attr("x", d => x(d.preference) + x.bandwidth()/2)
      .attr("y", d => y(d.mislabeled_value) - 15)
      .attr("text-anchor", "middle")
      .text(d => `${{d.mislabeled_value}}%`)
      .style("font-size", "12px");
  </script>
</body>
</html>"""
    clean_html_path = task_dir / "clean_source.html"
    clean_html_path.write_text(clean_html, encoding="utf-8")
    screenshot_html(clean_html_path, dest)
    return {
        "renderer": "d3_playwright",
        "plot_type": task.get("plot_type"),
        "misleader_type": task.get("misleader_type"),
        "cleaning_rule": "source-like_scatter_positions_use_true_labeled_values",
        "clean_source_html": rel(clean_html_path),
        "scatter_y_column": "mislabeled_value",
    }


def render_cherry_picking_scatter_source_chart(task: dict[str, Any], csv_path: Path, dest: Path, task_dir: Path) -> dict[str, Any]:
    df = clean_dataframe(csv_path)
    if "Month" not in df.columns:
        raise ValueError(f"{task.get('official_slug')} expected Month column")
    if {"Limited_AdSpend", "Limited_Sales"}.issubset(df.columns):
        x_col = "Limited_AdSpend"
        y_col = "Limited_Sales"
    elif {"AdSpend", "Sales"}.issubset(df.columns):
        x_col = "AdSpend"
        y_col = "Sales"
    else:
        raise ValueError(f"{task.get('official_slug')} expected Limited_AdSpend/Limited_Sales or AdSpend/Sales columns")
    slug = task.get("official_slug")
    if slug == "b017":
        added_rows = [
            {"Month": "Store 6", x_col: 30, y_col: 155},
            {"Month": "Store 7", x_col: 40, y_col: 82},
            {"Month": "Store 8", x_col: 50, y_col: 145},
            {"Month": "Store 9", x_col: 60, y_col: 90},
            {"Month": "Store 10", x_col: 70, y_col: 115},
        ]
    elif slug == "b034":
        added_rows = [
            {"Month": "Region F", x_col: 25, y_col: 119},
            {"Month": "Region G", x_col: 45, y_col: 83},
            {"Month": "Region H", x_col: 80, y_col: 103},
        ]
    elif slug == "b033":
        added_rows = [
            {"Month": "Q1", x_col: 25, y_col: 124},
            {"Month": "Q7", x_col: 75, y_col: 98},
            {"Month": "Q8", x_col: 85, y_col: 110},
        ]
    elif slug == "b032":
        added_rows = [
            {"Month": "Line F", x_col: 25, y_col: 126},
            {"Month": "Line G", x_col: 45, y_col: 82},
            {"Month": "Line H", x_col: 80, y_col: 105},
        ]
    elif slug == "b031":
        added_rows = [
            {"Month": "Week 1", x_col: 25, y_col: 119},
            {"Month": "Week 2", x_col: 45, y_col: 84},
            {"Month": "Week 12", x_col: 80, y_col: 101},
        ]
    elif slug == "b030":
        added_rows = [
            {"Month": "Store 1", x_col: 25, y_col: 125},
            {"Month": "Store 2", x_col: 45, y_col: 78},
            {"Month": "Store 3", x_col: 80, y_col: 104},
        ]
    elif slug == "b029":
        added_rows = [
            {"Month": "Region F", x_col: 25, y_col: 121},
            {"Month": "Region G", x_col: 45, y_col: 74},
            {"Month": "Region H", x_col: 80, y_col: 101},
        ]
    elif slug == "b028":
        added_rows = [
            {"Month": "June", x_col: 75, y_col: 105},
            {"Month": "July", x_col: 85, y_col: 95},
            {"Month": "August", x_col: 95, y_col: 118},
        ]
    elif slug == "b027":
        added_rows = [
            {"Month": "Region F", x_col: 25, y_col: 124},
            {"Month": "Region G", x_col: 45, y_col: 76},
            {"Month": "Region H", x_col: 80, y_col: 102},
        ]
    elif slug == "b026":
        added_rows = [
            {"Month": "Q1", x_col: 25, y_col: 122},
            {"Month": "Q7", x_col: 75, y_col: 92},
            {"Month": "Q8", x_col: 85, y_col: 106},
        ]
    elif slug == "b025":
        added_rows = [
            {"Month": "Week 1", x_col: 18, y_col: 118},
            {"Month": "Week 7", x_col: 72, y_col: 96},
            {"Month": "Week 8", x_col: 82, y_col: 108},
        ]
    elif slug == "b024":
        added_rows = [
            {"Month": "Q1", x_col: 25, y_col: 118},
            {"Month": "Q7", x_col: 75, y_col: 94},
            {"Month": "Q8", x_col: 85, y_col: 108},
        ]
    elif slug == "b023":
        added_rows = [
            {"Month": "January", x_col: 25, y_col: 118},
            {"Month": "February", x_col: 35, y_col: 82},
            {"Month": "March", x_col: 45, y_col: 126},
            {"Month": "April", x_col: 55, y_col: 91},
            {"Month": "October", x_col: 80, y_col: 104},
            {"Month": "November", x_col: 65, y_col: 88},
            {"Month": "December", x_col: 75, y_col: 96},
        ]
    elif slug == "b022":
        added_rows = [
            {"Month": "Region F", x_col: 25, y_col: 128},
            {"Month": "Region G", x_col: 38, y_col: 74},
            {"Month": "Region H", x_col: 52, y_col: 118},
            {"Month": "Region I", x_col: 62, y_col: 86},
            {"Month": "Region J", x_col: 80, y_col: 101},
        ]
    elif slug == "b021":
        added_rows = [
            {"Month": "Week 1", x_col: 25, y_col: 122},
            {"Month": "Week 2", x_col: 35, y_col: 78},
            {"Month": "Week 3", x_col: 45, y_col: 132},
            {"Month": "Week 4", x_col: 55, y_col: 88},
            {"Month": "Week 5", x_col: 65, y_col: 104},
            {"Month": "Week 6", x_col: 75, y_col: 92},
        ]
    elif slug == "b020":
        added_rows = [
            {"Month": "64–70", x_col: 80, y_col: 102},
        ]
    elif slug == "b019":
        added_rows = [
            {"Month": "Store 1", x_col: 25, y_col: 140},
            {"Month": "Store 2", x_col: 38, y_col: 74},
            {"Month": "Store 3", x_col: 45, y_col: 152},
            {"Month": "Store 4", x_col: 55, y_col: 88},
            {"Month": "Store 5", x_col: 62, y_col: 105},
        ]
    else:
        added_rows = [
            {"Month": "Store 1", x_col: 25, y_col: 118},
            {"Month": "Store 2", x_col: 35, y_col: 72},
            {"Month": "Store 3", x_col: 45, y_col: 135},
            {"Month": "Store 4", x_col: 55, y_col: 82},
            {"Month": "Store 5", x_col: 65, y_col: 96},
        ]

    def clean_number(value: Any) -> int | float:
        number = float(value)
        return int(number) if number.is_integer() else number

    original_rows = [
        {
            "Month": str(row["Month"]),
            x_col: clean_number(row[x_col]),
            y_col: clean_number(row[y_col]),
        }
        for _, row in df.iterrows()
    ]
    original_first_slugs = {"b017"} | {f"b{i:03d}" for i in range(20, 35)}
    data = original_rows + added_rows if slug in original_first_slugs else added_rows + original_rows
    clean_csv_path = task_dir / "clean_source.csv"
    with clean_csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["Month", x_col, y_col])
        writer.writeheader()
        writer.writerows(data)

    corrected_titles = {
        "b017": "All Stores: Ad Spend vs Sales",
        "b020": "Age Groups: Ad Spend vs Sales",
        "b021": "Campaign Weeks: Ad Spend vs Sales",
        "b022": "Regions: Ad Spend vs Sales",
        "b023": "Months: Ad Spend vs Sales",
        "b024": "Quarters: Ad Spend vs Sales",
        "b025": "Campaign Weeks: Ad Spend vs Sales",
        "b026": "Quarters: Ad Spend vs Sales",
        "b027": "Regions: Ad Spend vs Sales",
        "b028": "Advertising Budget vs Revenue (All Observations)",
        "b029": "Regions: Ad Spend vs Sales",
        "b030": "All Stores: Ad Spend vs Sales",
        "b031": "Campaign Weeks: Ad Spend vs Sales",
        "b032": "Product Lines: Ad Spend vs Sales",
        "b033": "Quarters: Ad Spend vs Sales",
        "b034": "Regions: Ad Spend vs Sales",
    }
    title = corrected_titles.get(str(slug), "All Stores: Ad Spend vs Sales")
    source_json = json.dumps(data, ensure_ascii=False)
    clean_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html.escape(title)}</title>
    <script src="https://d3js.org/d3.v6.min.js"></script>
    <style>
        #chart {{
            width: 1000px;
            height: 750px;
            margin: 60px auto;
        }}
        .dot {{ fill: steelblue; opacity: 0.8; }}
        .axis path, .axis line {{ stroke: #000; }}
        .month-label {{
            font-size: 10px;
            fill: #333;
            text-anchor: middle;
            font-weight: bold;
        }}
    </style>
</head>
<body>
    <h1>{html.escape(title)}</h1>
    <div id="chart"></div>
    <script>
        const margin = {{top: 40, right: 30, bottom: 50, left: 70}};
        const width = 1000 - margin.left - margin.right;
        const height = 750 - margin.top - margin.bottom;

        const svg = d3.select("#chart").append("svg")
          .attr("width", width + margin.left + margin.right)
          .attr("height", height + margin.top + margin.bottom);

        const g = svg.append("g").attr("transform", `translate(${{margin.left}},${{margin.top}})`);
        const data = {source_json};

        data.forEach(d => {{
          d[{json.dumps(x_col)}] = +d[{json.dumps(x_col)}];
          d[{json.dumps(y_col)}] = +d[{json.dumps(y_col)}];
        }});

        const x = d3.scaleLinear()
          .domain([d3.min(data, d => d[{json.dumps(x_col)}]) - 5, d3.max(data, d => d[{json.dumps(x_col)}]) + 5])
          .range([0, width]);

        const y = d3.scaleLinear()
          .domain([d3.min(data, d => d[{json.dumps(y_col)}]) - 10, d3.max(data, d => d[{json.dumps(y_col)}]) + 10])
          .range([height, 0]);

        g.append("g").attr("transform", `translate(0,${{height}})`).call(d3.axisBottom(x));
        g.append("g").call(d3.axisLeft(y));

        g.append("text")
          .attr("x", width / 2)
          .attr("y", height + 40)
          .attr("text-anchor", "middle")
          .style("font-size", "12px")
          .text("Advertising Spend ($ thousands)");

        g.append("text")
          .attr("transform", "rotate(-90)")
          .attr("x", -height / 2)
          .attr("y", -50)
          .attr("text-anchor", "middle")
          .style("font-size", "12px")
          .text("Sales ($ thousands)");

        g.selectAll(".dot")
          .data(data)
          .enter().append("circle")
          .attr("class", "dot")
          .attr("cx", d => x(d[{json.dumps(x_col)}]))
          .attr("cy", d => y(d[{json.dumps(y_col)}]))
          .attr("r", 5);

        g.selectAll(".month-label")
          .data(data)
          .enter().append("text")
          .attr("class", "month-label")
          .attr("x", d => x(d[{json.dumps(x_col)}]))
          .attr("y", d => y(d[{json.dumps(y_col)}]) - 15)
          .text(d => d.Month);
    </script>
</body>
</html>"""
    clean_html_path = task_dir / "clean_source.html"
    clean_html_path.write_text(clean_html, encoding="utf-8")
    screenshot_html(clean_html_path, dest)
    return {
        "renderer": "d3_playwright",
        "plot_type": task.get("plot_type"),
        "misleader_type": task.get("misleader_type"),
        "cleaning_rule": "source-like_scatter_adds_omitted_non_monotonic_context_data",
        "clean_source_html": rel(clean_html_path),
        "clean_source_csv": rel(clean_csv_path),
        "added_clean_rows": [row["Month"] for row in added_rows],
        "corrected_title": title,
    }


def render_data_visual_disproportion_bar_source_chart(task: dict[str, Any], csv_path: Path, dest: Path, task_dir: Path) -> dict[str, Any]:
    df = clean_dataframe(csv_path)
    label_col = "browser" if "browser" in df.columns else "smartphone_brand" if "smartphone_brand" in df.columns else None
    required = {"market_share", "color"}
    if not label_col or not required.issubset(df.columns):
        raise ValueError(f"{task.get('official_slug')} expected a category column, market_share, and color columns")
    data = [
        {
            "category": str(row[label_col]),
            "market_share": float(row["market_share"]),
            "color": str(row["color"]),
        }
        for _, row in df.iterrows()
    ]
    y_max = max(100.0, max(item["market_share"] for item in data) * 1.2)
    title = chart_title(task)
    source_json = json.dumps(data, ensure_ascii=False)
    clean_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(title)}</title>
  <script src="https://d3js.org/d3.v7.min.js"></script>
  <style>
    #chart {{ width: 1000px; height: 750px; margin: 40px auto; }}
    .text {{ font-size: 24px; font-weight: bold; fill: black; }}
    .axis path, .axis line {{ stroke: black; }}
  </style>
</head>
<body>
  <h1>{html.escape(title)}</h1>
  <div id="chart"></div>
  <script>
    const margin = {{ top: 20, right: 20, bottom: 40, left: 60 }};
    const width = 1000 - margin.left - margin.right;
    const height = 750 - margin.top - margin.bottom;
    const svg = d3.select("#chart").append("svg")
      .attr("width", width + margin.left + margin.right)
      .attr("height", height + margin.top + margin.bottom)
      .append("g")
      .attr("transform", `translate(${{margin.left}},${{margin.top}})`);

    const data = {source_json};
    const x = d3.scaleBand()
      .domain(data.map(d => d.category))
      .range([0, width])
      .padding(0.3);
    const y = d3.scaleLinear()
      .domain([0, {y_max}])
      .range([height, 0]);

    svg.append("g").attr("transform", `translate(0,${{height}})`).call(d3.axisBottom(x));
    svg.append("g").call(d3.axisLeft(y));

    svg.selectAll(".bar").data(data).enter().append("rect")
      .attr("class", "bar")
      .attr("x", d => x(d.category))
      .attr("y", d => y(d.market_share))
      .attr("width", x.bandwidth())
      .attr("height", d => height - y(d.market_share))
      .attr("fill", d => d.color);

    svg.selectAll(".text").data(data).enter().append("text")
      .attr("class", "text")
      .attr("x", d => x(d.category) + x.bandwidth() / 2)
      .attr("y", d => y(d.market_share) - 10)
      .attr("text-anchor", "middle")
      .text(d => `${{d.market_share}}%`);
  </script>
</body>
</html>"""
    clean_html_path = task_dir / "clean_source.html"
    clean_html_path.write_text(clean_html, encoding="utf-8")
    screenshot_html(clean_html_path, dest)
    return {
        "renderer": "d3_playwright",
        "plot_type": task.get("plot_type"),
        "misleader_type": task.get("misleader_type"),
        "cleaning_rule": "source-like_bar_heights_use_true_market_share",
        "clean_source_html": rel(clean_html_path),
        "bar_value_column": "market_share",
        "bar_category_column": label_col,
    }


def render_energy_production_bar_source_chart(task: dict[str, Any], csv_path: Path, dest: Path, task_dir: Path) -> dict[str, Any]:
    df = clean_dataframe(csv_path)
    required = {"energy_source", "production_percentage", "color"}
    if not required.issubset(df.columns):
        raise ValueError(f"{task.get('official_slug')} expected energy_source, production_percentage, and color columns")
    data = [
        {
            "energy_source": str(row["energy_source"]),
            "production_percentage": float(row["production_percentage"]),
            "color": str(row["color"]),
        }
        for _, row in df.iterrows()
    ]
    title = chart_title(task)
    source_json = json.dumps(data, ensure_ascii=False)
    clean_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html.escape(title)}</title>
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <style>
        #chart {{
            width: 1000px;
            height: 750px;
            margin: 40px auto;
        }}
        .text {{
            font-size: 24px;
            font-weight: bold;
            fill: black;
        }}
        .label {{
            font-size: 18px;
            fill: black;
        }}
        .axis path, .axis line {{
            stroke: black;
        }}
    </style>
</head>
<body>
    <h1>{html.escape(title)}</h1>
    <div id="chart"></div>
    <script>
        const margin = {{ top: 20, right: 20, bottom: 40, left: 60 }};
        const width = 1000 - margin.left - margin.right;
        const height = 750 - margin.top - margin.bottom;

        const svg = d3.select("#chart").append("svg")
            .attr("width", width + margin.left + margin.right)
            .attr("height", height + margin.top + margin.bottom)
            .append("g")
            .attr("transform", `translate(${{margin.left}},${{margin.top}})`);

        const data = {source_json};
        const x = d3.scaleBand()
            .domain(data.map(d => d.energy_source))
            .range([0, width])
            .padding(0.3);
        const y = d3.scaleLinear()
            .domain([0, 70])
            .range([height, 0]);

        svg.append("g")
            .attr("transform", `translate(0,${{height}})`)
            .call(d3.axisBottom(x));
        svg.append("g").call(d3.axisLeft(y));

        svg.selectAll(".bar")
            .data(data)
            .enter()
            .append("rect")
            .attr("class", "bar")
            .attr("x", d => x(d.energy_source))
            .attr("y", d => y(d.production_percentage))
            .attr("width", x.bandwidth())
            .attr("height", d => height - y(d.production_percentage))
            .attr("fill", d => d.color);

        svg.selectAll(".text")
            .data(data)
            .enter()
            .append("text")
            .attr("class", "text")
            .attr("x", d => x(d.energy_source) + x.bandwidth() / 2)
            .attr("y", d => y(d.production_percentage) - 10)
            .attr("text-anchor", "middle")
            .text(d => `${{d.production_percentage}}%`);
    </script>
</body>
</html>"""
    clean_html_path = task_dir / "clean_source.html"
    clean_html_path.write_text(clean_html, encoding="utf-8")
    screenshot_html(clean_html_path, dest)
    return {
        "renderer": "d3_playwright",
        "plot_type": task.get("plot_type"),
        "misleader_type": task.get("misleader_type"),
        "cleaning_rule": "source-like_bar_heights_use_true_production_percentage",
        "clean_source_html": rel(clean_html_path),
        "bar_category_column": "energy_source",
        "bar_value_column": "production_percentage",
        "ignored_misleading_column": "bar_height",
    }


def render_rewrite_reported_percentage_bar_source_chart(task: dict[str, Any], csv_path: Path, dest: Path, task_dir: Path) -> dict[str, Any]:
    df = clean_dataframe(csv_path)
    required = {"category", "reported_percentage", "color"}
    if not required.issubset(df.columns):
        raise ValueError(f"{task.get('official_slug')} expected category, reported_percentage, and color columns")
    data = [
        {
            "category": str(row["category"]),
            "reported_percentage": float(row["reported_percentage"]),
            "color": str(row["color"]),
        }
        for _, row in df.iterrows()
    ]
    title = chart_title(task)
    source_json = json.dumps(data, ensure_ascii=False)
    clean_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html.escape(title)}</title>
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <style>
        #chart {{
            width: 1000px;
            height: 750px;
            margin: 40px auto;
        }}
        .text {{
            font-size: 24px;
            font-weight: bold;
            fill: black;
        }}
        .label {{
            font-size: 18px;
            fill: black;
        }}
        .axis path, .axis line {{
            stroke: black;
        }}
    </style>
</head>
<body>
    <h1>{html.escape(title)}</h1>
    <div id="chart"></div>
    <script>
        const margin = {{ top: 20, right: 20, bottom: 40, left: 60 }};
        const width = 1000 - margin.left - margin.right;
        const height = 750 - margin.top - margin.bottom;

        const svg = d3.select("#chart").append("svg")
            .attr("width", width + margin.left + margin.right)
            .attr("height", height + margin.top + margin.bottom)
            .append("g")
            .attr("transform", `translate(${{margin.left}},${{margin.top}})`);

        const data = {source_json};
        const x = d3.scaleBand()
            .domain(data.map(d => d.category))
            .range([0, width])
            .padding(0.3);
        const y = d3.scaleLinear()
            .domain([0, 70])
            .range([height, 0]);

        svg.append("g")
            .attr("transform", `translate(0,${{height}})`)
            .call(d3.axisBottom(x));
        svg.append("g").call(d3.axisLeft(y));

        svg.selectAll(".bar")
            .data(data)
            .enter()
            .append("rect")
            .attr("class", "bar")
            .attr("x", d => x(d.category))
            .attr("y", d => y(d.reported_percentage))
            .attr("width", x.bandwidth())
            .attr("height", d => height - y(d.reported_percentage))
            .attr("fill", d => d.color);

        svg.selectAll(".text")
            .data(data)
            .enter()
            .append("text")
            .attr("class", "text")
            .attr("x", d => x(d.category) + x.bandwidth() / 2)
            .attr("y", d => y(d.reported_percentage) - 10)
            .attr("text-anchor", "middle")
            .text(d => `${{d.reported_percentage}}%`);
    </script>
</body>
</html>"""
    clean_html_path = task_dir / "clean_source.html"
    clean_html_path.write_text(clean_html, encoding="utf-8")
    screenshot_html(clean_html_path, dest)
    return {
        "renderer": "d3_playwright",
        "plot_type": task.get("plot_type"),
        "misleader_type": task.get("misleader_type"),
        "cleaning_rule": "source-like_bar_heights_use_true_reported_percentage",
        "clean_source_html": rel(clean_html_path),
        "bar_category_column": "category",
        "bar_value_column": "reported_percentage",
        "ignored_misleading_column": "visual_block_height",
    }


def render_misleading_annotation_line_source_chart(task: dict[str, Any], csv_path: Path, dest: Path, task_dir: Path) -> dict[str, Any]:
    df = clean_dataframe(csv_path)
    x_col = "quarter" if "quarter" in df.columns else "year" if "year" in df.columns else None
    if not x_col:
        raise ValueError(f"{task.get('official_slug')} expected year or quarter column")
    y_col = (
        "population"
        if "population" in df.columns
        else "tourists"
        if "tourists" in df.columns
        else "production"
        if "production" in df.columns
        else "revenue"
        if "revenue" in df.columns
        else None
    )
    if not y_col:
        raise ValueError(f"{task.get('official_slug')} expected a supported value column")
    data = [
        {x_col: str(row[x_col]), y_col: float(row[y_col])}
        for _, row in df.iterrows()
    ]
    fallback_y_max = max(item[y_col] for item in data) * 1.1
    y_max = source_y_domain_max(task, fallback_y_max)
    source_text = source_html_text(task)
    line_class = "lineC" if ".lineC" in source_text else "line"
    if task.get("official_slug") == "b039":
        title = "factory F from 2018 to 2023"
        y_label = "Production"
    elif y_col == "population":
        title = "Increasing Population of City A from 2010 to 2015"
        y_label = "Population"
    elif y_col == "production":
        title = "Decreasing Production at Factory F from 2018 to 2023"
        y_label = "Production"
    elif y_col == "revenue":
        title = "Increasing Revenue of Company C from Q1 to Q4"
        y_label = "Revenue"
    else:
        title = "Increasing Number of New Tourists in Town Z from 1880 to 1891"
        y_label = "Number of New Tourists" if "Number of New Tourists" in source_text else "Number of Tourists"
    x_label = "Quarter" if x_col == "quarter" else "Year"
    cleaning_rule = (
        "source-like_line_chart_neutral_title"
        if task.get("official_slug") == "b039"
        else "source-like_line_chart_corrected_directional_title"
    )
    source_json = json.dumps(data, ensure_ascii=False)
    clean_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Line Chart</title>
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <style>
        #chart {{ width: 1000px; height: 750px; margin: 60px auto; }}
        .line, .lineC {{ fill: none; stroke: steelblue; stroke-width: 3px; }}
        .axis path, .axis line {{ stroke: black; }}
    </style>
</head>
<body>
    <h1>{html.escape(title)}</h1>
    <div id="chart"></div>
    <script>
        const margin = {{top: 40, right: 20, bottom: 40, left: 60}};
        const width = 1000 - margin.left - margin.right;
        const height = 750 - margin.top - margin.bottom;
        const g = d3.select("#chart").append("svg")
            .attr("width", width + margin.left + margin.right)
            .attr("height", height + margin.top + margin.bottom)
            .append("g").attr("transform", `translate(${{margin.left}},${{margin.top}})`);
        const data = {source_json};
        const x = d3.scalePoint().domain(data.map(d => d[{json.dumps(x_col)}])).range([0, width]);
        const y = d3.scaleLinear().domain([0, {y_max}]).range([height, 0]);
        const line = d3.line().x(d => x(d[{json.dumps(x_col)}])).y(d => y(d[{json.dumps(y_col)}]));
        g.append("g").attr("transform", `translate(0,${{height}})`).call(d3.axisBottom(x));
        g.append("g").call(d3.axisLeft(y));
        g.append("text").attr("x", width/2).attr("y", height + 35).attr("text-anchor", "middle").text({json.dumps(x_label)});
        g.append("text").attr("transform", "rotate(-90)").attr("x", -height/2).attr("y", -45).attr("text-anchor", "middle").text({json.dumps(y_label)});
        g.append("path").datum(data).attr("class", {json.dumps(line_class)}).attr("d", line);
    </script>
</body>
</html>"""
    clean_html_path = task_dir / "clean_source.html"
    clean_html_path.write_text(clean_html, encoding="utf-8")
    screenshot_html(clean_html_path, dest)
    return {
        "renderer": "d3_playwright",
        "plot_type": task.get("plot_type"),
        "misleader_type": task.get("misleader_type"),
        "cleaning_rule": cleaning_rule,
        "clean_source_html": rel(clean_html_path),
        "corrected_title": title,
        "line_x_column": x_col,
        "line_y_column": y_col,
        "line_y_domain_max": y_max,
    }


def render_rewrite_neutral_title_line_source_chart(task: dict[str, Any], csv_path: Path, dest: Path, task_dir: Path) -> dict[str, Any]:
    df = clean_dataframe(csv_path)
    if "year" not in df.columns or "value" not in df.columns:
        raise ValueError(f"{task.get('official_slug')} expected year and value columns")
    data = [
        {"year": str(int(row["year"])), "value": float(row["value"])}
        for _, row in df.iterrows()
    ]
    slug = task.get("official_slug")
    title_map = {
        "env029": "Clean Grid Output from 2018 to 2023",
        "env030": "Regional Air Quality Recovery from 2018 to 2023",
        "env031": "River Restoration Capacity from 2018 to 2023",
    }
    y_label_map = {
        "env029": "Grid Output (GWh)",
        "env030": "Recovery Score",
        "env031": "Capacity Index",
    }
    title = title_map.get(str(slug), chart_title(task).removeprefix("Increasing ").strip())
    y_label = y_label_map.get(str(slug), "Value")
    original_title = chart_title(task)
    y_max = max(item["value"] for item in data) * 1.12
    source_json = json.dumps(data, ensure_ascii=False)
    clean_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(title)}</title>
  <script src="https://d3js.org/d3.v7.min.js"></script>
  <style>
    #chart {{
      width: 1000px;
      height: 750px;
      margin: 50px auto;
    }}
    .line {{ fill: none; stroke: #4f7faf; stroke-width: 4px; }}
    .axis path, .axis line {{ stroke: #000; stroke-width: 2px; }}
    .axis-label {{ font-size: 18px; text-anchor: middle; }}
  </style>
</head>
<body>
  <h1 style="text-align: center; font-family: serif; font-size: 34px; font-weight: bold;">{html.escape(title)}</h1>
  <div id="chart"></div>
  <script>
    const margin = {{top: 40, right: 50, bottom: 60, left: 90}};
    const width = 1000 - margin.left - margin.right;
    const height = 750 - margin.top - margin.bottom;
    const data = {source_json};

    const svg = d3.select("#chart").append("svg")
      .attr("width", width + margin.left + margin.right)
      .attr("height", height + margin.top + margin.bottom);
    const g = svg.append("g").attr("transform", `translate(${{margin.left}},${{margin.top}})`);

    const x = d3.scalePoint()
      .domain(data.map(d => d.year))
      .range([0, width]);
    const y = d3.scaleLinear()
      .domain([0, {y_max}])
      .range([height, 0]);

    const line = d3.line()
      .x(d => x(d.year))
      .y(d => y(d.value));

    g.append("g").attr("transform", `translate(0,${{height}})`).call(d3.axisBottom(x));
    g.append("g").call(d3.axisLeft(y).ticks(8).tickFormat(d3.format(",.0f")));

    svg.append("text")
      .attr("class", "axis-label")
      .attr("x", width / 2 + margin.left)
      .attr("y", height + margin.top + 45)
      .text("Year");

    svg.append("text")
      .attr("class", "axis-label")
      .attr("transform", "rotate(-90)")
      .attr("x", -height / 2 - margin.top)
      .attr("y", margin.left - 65)
      .text("{html.escape(y_label)}");

    g.append("path").datum(data).attr("class", "line").attr("d", line);
  </script>
</body>
</html>"""
    clean_html_path = task_dir / "clean_source.html"
    clean_html_path.write_text(clean_html, encoding="utf-8")
    screenshot_html(clean_html_path, dest)
    return {
        "renderer": "d3_playwright",
        "plot_type": task.get("plot_type"),
        "misleader_type": task.get("misleader_type"),
        "cleaning_rule": "source-like_line_chart_neutral_title",
        "clean_source_html": rel(clean_html_path),
        "line_x_column": "year",
        "line_y_column": "value",
        "corrected_title": title,
        "original_misleading_title": original_title,
        "line_y_domain_max": y_max,
    }


def render_health_svg_line_chart(
    task: dict[str, Any],
    csv_path: Path,
    dest: Path,
    task_dir: Path,
    *,
    title: str,
    subtitle: str,
    y_label: str,
    line_color: str,
    y_min: float,
    y_max: float,
    y_ticks: list[float],
    cleaning_rule: str,
    original_title: str | None = None,
) -> dict[str, Any]:
    df = clean_dataframe(csv_path)
    if "year" not in df.columns:
        raise ValueError(f"{task.get('official_slug')} expected year column")
    value_col = "value" if "value" in df.columns else next((col for col in ["visits", "requests", "cases", "referrals"] if col in df.columns), None)
    if not value_col:
        raise ValueError(f"{task.get('official_slug')} expected a supported value column")
    data = [{"year": int(row["year"]), "value": float(row[value_col])} for _, row in df.iterrows()]
    source_json = json.dumps(data, ensure_ascii=False)
    tick_json = json.dumps(y_ticks)
    subtitle_html = f'\n    <p class="subtitle">{html.escape(subtitle)}</p>' if subtitle else ""
    clean_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{html.escape(title)}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 0; background: #ffffff; color: #111827; }}
    .wrap {{ width: 1000px; margin: 32px auto; }}
    h1 {{ margin: 0 0 8px; font-size: 34px; }}
    .subtitle {{ margin: 0 0 18px; color: #4b5563; font-size: 18px; }}
    svg {{ width: 1000px; height: 720px; display: block; }}
    .axis {{ stroke: #111827; stroke-width: 1.2; }}
    .tick {{ stroke: #d1d5db; stroke-width: 1; }}
    .line {{ fill: none; stroke: {line_color}; stroke-width: 4; }}
    .dot {{ fill: {line_color}; }}
    .label {{ font-size: 16px; fill: #374151; }}
    .axis-label {{ font-size: 18px; fill: #111827; font-weight: 600; }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>{html.escape(title)}</h1>{subtitle_html}
    <svg viewBox="0 0 1000 720" aria-label="{html.escape(title)} chart"></svg>
  </div>
  <script>
    const data = {source_json};
    const svg = document.querySelector("svg");
    const ns = "http://www.w3.org/2000/svg";
    const margin = {{ top: 30, right: 40, bottom: 80, left: 90 }};
    const width = 1000 - margin.left - margin.right;
    const height = 720 - margin.top - margin.bottom;
    const xStep = width / (data.length - 1);
    const yMin = {y_min};
    const yMax = {y_max};
    const x = i => margin.left + i * xStep;
    const y = v => margin.top + (yMax - v) / (yMax - yMin) * height;
    function append(tag, attrs, parent = svg) {{
      const el = document.createElementNS(ns, tag);
      Object.entries(attrs || {{}}).forEach(([k, v]) => el.setAttribute(k, v));
      parent.appendChild(el);
      return el;
    }}
    append("line", {{ x1: margin.left, y1: margin.top + height, x2: margin.left + width, y2: margin.top + height, class: "axis" }});
    append("line", {{ x1: margin.left, y1: margin.top, x2: margin.left, y2: margin.top + height, class: "axis" }});
    {tick_json}.forEach(tick => {{
      const ty = y(tick);
      append("line", {{ x1: margin.left, y1: ty, x2: margin.left + width, y2: ty, class: "tick" }});
      const text = append("text", {{ x: margin.left - 12, y: ty + 5, "text-anchor": "end", class: "label" }});
      text.textContent = tick;
    }});
    data.forEach((d, i) => {{
      const tx = x(i);
      append("line", {{ x1: tx, y1: margin.top + height, x2: tx, y2: margin.top + height + 8, class: "axis" }});
      const text = append("text", {{ x: tx, y: margin.top + height + 28, "text-anchor": "middle", class: "label" }});
      text.textContent = d.year;
    }});
    const path = data.map((d, i) => `${{i === 0 ? "M" : "L"}} ${{x(i)}} ${{y(d.value)}}`).join(" ");
    append("path", {{ d: path, class: "line" }});
    data.forEach((d, i) => append("circle", {{ cx: x(i), cy: y(d.value), r: 5, class: "dot" }}));
    const xlabel = append("text", {{ x: margin.left + width / 2, y: 690, "text-anchor": "middle", class: "axis-label" }});
    xlabel.textContent = "Year";
    const ylabel = append("text", {{ x: 28, y: margin.top + height / 2, transform: `rotate(-90 28 ${{margin.top + height / 2}})`, "text-anchor": "middle", class: "axis-label" }});
    ylabel.textContent = "{html.escape(y_label)}";
  </script>
</body>
</html>"""
    clean_html_path = task_dir / "clean_source.html"
    clean_html_path.write_text(clean_html, encoding="utf-8")
    screenshot_html(clean_html_path, dest)
    return {
        "renderer": "svg_playwright",
        "plot_type": task.get("plot_type"),
        "misleader_type": task.get("misleader_type"),
        "cleaning_rule": cleaning_rule,
        "clean_source_html": rel(clean_html_path),
        "corrected_title": title,
        "original_misleading_title": original_title or chart_title(task),
        "line_x_column": "year",
        "line_y_column": value_col,
    }


def render_health_cherry_picking_line_source_chart(task: dict[str, Any], csv_path: Path, dest: Path, task_dir: Path) -> dict[str, Any]:
    slug = str(task.get("official_slug"))
    config = {
        "health006": ("Hospital Screening Referral Volume", "Referral volume (thousands)", "#ea580c", 80, 155, [80, 100, 120, 140]),
        "health007": ("Positive Test Rate at Sentinel Sites", "Positive test rate", "#7c3aed", 4.5, 8.3, [5, 6, 7, 8]),
        "health008": ("Respiratory Clinic Visits", "Clinic visits (thousands)", "#b91c1c", 110, 175, [120, 140, 160]),
        "health009": ("Telehealth Follow-up Enrollment Trend", "Enrolled patients", "#0f766e", 210, 380, [220, 260, 300, 340, 380]),
    }
    if slug not in config:
        raise ValueError(f"Unsupported health cherry-picking line task: {slug}")
    title, y_label, color, y_min, y_max, ticks = config[slug]
    return render_health_svg_line_chart(
        task,
        csv_path,
        dest,
        task_dir,
        title=title,
        subtitle="Full 2013-2020 record shown in dashboard summary",
        y_label=y_label,
        line_color=color,
        y_min=y_min,
        y_max=y_max,
        y_ticks=ticks,
        cleaning_rule="source-like_line_chart_full_2013_2020_window",
    )


def render_health_trend_title_line_source_chart(task: dict[str, Any], csv_path: Path, dest: Path, task_dir: Path) -> dict[str, Any]:
    slug = str(task.get("official_slug"))
    config = {
        "health016": ("Increasing Emergency Department Visits in Region Z from 2012 to 2023", "Regional monitoring record shown in the dashboard summary", "Emergency department visits", "#b91c1c", 0, 3950, [0, 800, 1600, 2400, 3200]),
        "health017": ("Increasing Telehealth Follow-up Requests from 2012 to 2023", "Program demand record shown in the dashboard summary", "Telehealth follow-up requests", "#0f766e", 0, 3200, [0, 800, 1600, 2400, 3200]),
        "health018": ("Increasing Respiratory Infection Cases in Sentinel Sites from 2012 to 2023", "Sentinel surveillance record shown in the dashboard summary", "Respiratory infection cases", "#7c3aed", 0, 3500, [0, 800, 1600, 2400, 3200]),
        "health019": ("Increasing Screening Referrals Across Hospitals from 2012 to 2023", "Referral-monitoring record shown in the dashboard summary", "Screening referrals", "#ea580c", 0, 4000, [0, 800, 1600, 2400, 3200, 4000]),
    }
    if slug not in config:
        raise ValueError(f"Unsupported health trend-title line task: {slug}")
    title, subtitle, y_label, color, y_min, y_max, ticks = config[slug]
    return render_health_svg_line_chart(
        task,
        csv_path,
        dest,
        task_dir,
        title=title,
        subtitle=subtitle,
        y_label=y_label,
        line_color=color,
        y_min=y_min,
        y_max=y_max,
        y_ticks=ticks,
        cleaning_rule="source-like_line_chart_corrected_increasing_title",
    )


def render_health_scatter_cherry_picking_source_chart(task: dict[str, Any], csv_path: Path, dest: Path, task_dir: Path) -> dict[str, Any]:
    slug = str(task.get("official_slug"))
    configs = {
        "health010": {
            "title": "Asthma Regions: PM2.5 Exposure vs ER Visits",
            "label_col": "Region",
            "x_col": "PM25_Exposure",
            "y_col": "ER_Visits",
            "color": "#b91c1c",
            "x_label": "PM2.5 exposure index",
            "y_label": "Asthma ER visits",
            "x_ticks": [30, 40, 50, 60, 70],
            "y_ticks": [60, 80, 100, 120, 140, 160],
            "x_min": 25,
            "x_max": 75,
            "y_min": 55,
            "y_max": 168,
            "added": [("Region F", 34, 145), ("Region G", 44, 63), ("Region H", 54, 132), ("Region I", 64, 91), ("Region J", 72, 118)],
        },
        "health011": {
            "title": "Screening Centers: Outreach Hours vs Referral Count",
            "label_col": "Screening_Center",
            "x_col": "Outreach_Hours",
            "y_col": "Referral_Count",
            "color": "#ea580c",
            "x_label": "Monthly outreach hours",
            "y_label": "Referral count",
            "x_ticks": [30, 40, 50, 60, 70],
            "y_ticks": [60, 80, 100, 120, 140, 160],
            "x_min": 28,
            "x_max": 77,
            "y_min": 55,
            "y_max": 170,
            "added": [("Center F", 34, 150), ("Center G", 46, 66), ("Center H", 58, 136), ("Center I", 68, 84), ("Center J", 75, 110)],
        },
        "health012": {
            "title": "Sentinel Sites: Testing Volume vs Positive Cases",
            "label_col": "Sentinel_Site",
            "x_col": "Testing_Volume",
            "y_col": "Positive_Cases",
            "color": "#7c3aed",
            "x_label": "Weekly testing volume (thousands)",
            "y_label": "Positive cases detected",
            "x_ticks": [30, 40, 50, 60, 70],
            "y_ticks": [60, 80, 100, 120, 140, 160],
            "x_min": 24,
            "x_max": 72,
            "y_min": 50,
            "y_max": 168,
            "added": [("Site F", 32, 140), ("Site G", 44, 62), ("Site H", 56, 128), ("Site I", 64, 83), ("Site J", 70, 108)],
        },
        "health013": {
            "title": "Hospitals: Nurse Hours vs Discharge Count",
            "label_col": "Hospital",
            "x_col": "Weekly_NurseHours",
            "y_col": "Discharge_Count",
            "color": "#0f766e",
            "x_label": "Weekly nurse hours (thousands)",
            "y_label": "Monthly discharge count (thousands)",
            "x_ticks": [30, 40, 50, 60, 70],
            "y_ticks": [60, 80, 100, 120, 140, 160],
            "x_min": 25,
            "x_max": 76,
            "y_min": 50,
            "y_max": 175,
            "added": [("Hospital F", 34, 150), ("Hospital G", 46, 68), ("Hospital H", 58, 132), ("Hospital I", 66, 86), ("Hospital J", 74, 112)],
        },
    }
    if slug not in configs:
        raise ValueError(f"Unsupported health scatter task: {slug}")
    cfg = configs[slug]
    df = clean_dataframe(csv_path)
    rows = [
        (str(row[cfg["label_col"]]), float(row[cfg["x_col"]]), float(row[cfg["y_col"]]))
        for _, row in df.iterrows()
    ]
    rows.extend(cfg["added"])
    clean_csv_path = task_dir / "clean_source.csv"
    with clean_csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([cfg["label_col"], cfg["x_col"], cfg["y_col"]])
        writer.writerows(rows)
    data = [{"label": label, "x": x, "y": y} for label, x, y in rows]
    source_json = json.dumps(data, ensure_ascii=False)
    x_ticks_json = json.dumps(cfg["x_ticks"])
    y_ticks_json = json.dumps(cfg["y_ticks"])
    clean_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{html.escape(cfg["title"])}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 0; background: #fff; color: #111827; }}
    .wrap {{ width: 1000px; margin: 32px auto; }}
    h1 {{ margin: 0 0 26px; font-size: 34px; }}
    svg {{ width: 1000px; height: 720px; display: block; }}
    .axis {{ stroke: #111827; stroke-width: 1.2; }}
    .tick {{ stroke: #d1d5db; stroke-width: 1; }}
    .dot {{ fill: {cfg["color"]}; opacity: 0.88; }}
    .label {{ font-size: 15px; fill: #374151; font-weight: 700; }}
    .axis-label {{ font-size: 18px; fill: #111827; font-weight: 600; }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>{html.escape(cfg["title"])}</h1>
    <svg viewBox="0 0 1000 720" aria-label="{html.escape(cfg["title"])} scatter plot"></svg>
  </div>
  <script>
    const data = {source_json};
    const svg = document.querySelector("svg");
    const ns = "http://www.w3.org/2000/svg";
    const margin = {{ top: 30, right: 40, bottom: 80, left: 90 }};
    const width = 1000 - margin.left - margin.right;
    const height = 720 - margin.top - margin.bottom;
    const xMin = {cfg["x_min"]}, xMax = {cfg["x_max"]}, yMin = {cfg["y_min"]}, yMax = {cfg["y_max"]};
    const x = v => margin.left + (v - xMin) / (xMax - xMin) * width;
    const y = v => margin.top + (yMax - v) / (yMax - yMin) * height;
    function append(tag, attrs, parent = svg) {{
      const el = document.createElementNS(ns, tag);
      for (const [k, v] of Object.entries(attrs || {{}})) el.setAttribute(k, v);
      parent.appendChild(el);
      return el;
    }}
    append("line", {{ x1: margin.left, y1: margin.top + height, x2: margin.left + width, y2: margin.top + height, class: "axis" }});
    append("line", {{ x1: margin.left, y1: margin.top, x2: margin.left, y2: margin.top + height, class: "axis" }});
    {x_ticks_json}.forEach(v => {{
      const tx = x(v);
      append("line", {{ x1: tx, y1: margin.top, x2: tx, y2: margin.top + height, class: "tick" }});
      const t = append("text", {{ x: tx, y: margin.top + height + 28, "text-anchor": "middle", class: "label" }});
      t.textContent = v;
    }});
    {y_ticks_json}.forEach(v => {{
      const ty = y(v);
      append("line", {{ x1: margin.left, y1: ty, x2: margin.left + width, y2: ty, class: "tick" }});
      const t = append("text", {{ x: margin.left - 12, y: ty + 5, "text-anchor": "end", class: "label" }});
      t.textContent = v;
    }});
    data.forEach(d => {{
      append("circle", {{ cx: x(d.x), cy: y(d.y), r: 7, class: "dot" }});
      const t = append("text", {{ x: x(d.x), y: y(d.y) - 14, "text-anchor": "middle", class: "label" }});
      t.textContent = d.label;
    }});
    const xlabel = append("text", {{ x: margin.left + width / 2, y: 690, "text-anchor": "middle", class: "axis-label" }});
    xlabel.textContent = "{html.escape(cfg["x_label"])}";
    const ylabel = append("text", {{ x: 30, y: margin.top + height / 2, transform: `rotate(-90 30 ${{margin.top + height / 2}})`, "text-anchor": "middle", class: "axis-label" }});
    ylabel.textContent = "{html.escape(cfg["y_label"])}";
  </script>
</body>
</html>"""
    clean_html_path = task_dir / "clean_source.html"
    clean_html_path.write_text(clean_html, encoding="utf-8")
    screenshot_html(clean_html_path, dest)
    return {
        "renderer": "svg_playwright",
        "plot_type": task.get("plot_type"),
        "misleader_type": task.get("misleader_type"),
        "cleaning_rule": "source-like_scatter_adds_omitted_non_monotonic_health_context_data",
        "clean_source_html": rel(clean_html_path),
        "clean_source_csv": rel(clean_csv_path),
        "corrected_title": cfg["title"],
        "original_misleading_title": chart_title(task),
        "scatter_x_column": cfg["x_col"],
        "scatter_y_column": cfg["y_col"],
        "added_clean_rows": [row[0] for row in cfg["added"]],
    }


def render_pub030_pie_source_chart(task: dict[str, Any], csv_path: Path, dest: Path, task_dir: Path) -> dict[str, Any]:
    df = clean_dataframe(csv_path)
    if "mode" not in df.columns or "share" not in df.columns:
        raise ValueError("pub030 expected mode and share columns")
    data = [
        {"mode": str(row["mode"]), "share": float(row["share"])}
        for _, row in df.iterrows()
    ]
    title = chart_title(task)
    source_json = json.dumps(data, ensure_ascii=False)
    clean_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pie Chart</title>
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <style>
        #chart {{ width: 1000px; height: 750px; margin: 60px auto; }}
        .slice-text {{ font-size: 14px; font-weight: bold; fill: white; }}
        .legend text {{ font-size: 12px; }}
    </style>
</head>
<body>
    <h1>{html.escape(title)}</h1>
    <div id="chart"></div>
    <script>
        const width = 800, height = 700, radius = Math.min(width, height) / 2;
        const svg = d3.select("#chart").append("svg").attr("width", width + 200).attr("height", height + 50)
            .append("g").attr("transform", `translate(${{width/2}}, ${{height/2}})`);
        const data = {source_json};
        const color = d3.scaleOrdinal()
            .domain(data.map(d => d.mode))
            .range(["#4E79A7", "#59A14F"]);
        const pie = d3.pie().value(d => d.share);
        const arc = d3.arc().innerRadius(0).outerRadius(radius);
        svg.selectAll("path").data(pie(data)).enter().append("path").attr("d", arc).attr("fill", d => color(d.data.mode));
        svg.selectAll("text.slice-text").data(pie(data)).enter().append("text").attr("class", "slice-text")
            .attr("transform", d => `translate(${{arc.centroid(d)}})`).attr("text-anchor", "middle").text(d => `${{d.data.share}}%`);
        const legend = svg.append("g").attr("transform", `translate(${{radius + 20}}, ${{-radius}})`);
        legend.selectAll("rect").data(data).enter().append("rect").attr("x", 0).attr("y", (d,i) => i*25).attr("width", 18).attr("height", 18).attr("fill", d => color(d.mode));
        legend.selectAll("text").data(data).enter().append("text").attr("x", 25).attr("y", (d,i) => i*25+13).text(d => d.mode);
    </script>
</body>
</html>"""
    clean_html_path = task_dir / "clean_source.html"
    clean_html_path.write_text(clean_html, encoding="utf-8")
    screenshot_html(clean_html_path, dest)
    return {
        "renderer": "d3_playwright",
        "plot_type": task.get("plot_type"),
        "misleader_type": task.get("misleader_type"),
        "cleaning_rule": "source-like_pie_chart_neutral_categorical_colors_true_shares",
        "clean_source_html": rel(clean_html_path),
        "pie_value_column": "share",
    }


def render_cumulative_grouped_bar_source_chart(task: dict[str, Any], csv_path: Path, dest: Path, task_dir: Path) -> dict[str, Any]:
    df = clean_dataframe(csv_path)
    if "Quarter" not in df.columns:
        raise ValueError(f"{task.get('official_slug')} expected Quarter column")
    categories = [col for col in df.columns if col != "Quarter"]
    if not categories:
        raise ValueError(f"{task.get('official_slug')} expected metric columns")
    data = df.to_dict("records")
    for row in data:
        for category in categories:
            row[category] = float(row[category])
    value_max = max(float(row[category]) for row in data for category in categories)
    source_json = json.dumps(data, ensure_ascii=False)
    categories_json = json.dumps(categories, ensure_ascii=False)
    title = chart_title(task)
    clean_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(title)}</title>
  <script src="https://d3js.org/d3.v7.min.js"></script>
  <style>
    .bar {{ width: 30px; margin: 1px; }}
    .axis path, .axis line {{ shape-rendering: crispEdges; }}
    .legend {{ font-size: 12px; }}
  </style>
</head>
<body>
  <h1>{html.escape(title)}</h1>
  <svg width="1000" height="750"></svg>
  <script>
    const margin = {{ top: 30, right: 80, bottom: 60, left: 60 }};
    const width = 1000 - margin.left - margin.right;
    const height = 750 - margin.top - margin.bottom;

    const svg = d3.select("svg")
      .attr("width", width + margin.left + margin.right)
      .attr("height", height + margin.top + margin.bottom)
      .append("g")
      .attr("transform", "translate(" + margin.left + "," + margin.top + ")");

    const data = {source_json};
    const categories = {categories_json};
    const groups = data.map(d => d.Quarter);

    const x = d3.scaleBand()
      .domain(groups)
      .range([0, width])
      .padding(0.1);

    const xSub = d3.scaleBand()
      .domain(categories)
      .range([0, x.bandwidth()])
      .padding(0.08);

    const y = d3.scaleLinear()
      .domain([0, {value_max}])
      .nice()
      .range([height, 0]);

    const color = d3.scaleOrdinal().domain(categories).range(d3.schemeCategory10);

    const xAxis = svg.append("g")
      .attr("transform", "translate(0," + height + ")")
      .call(d3.axisBottom(x));
    xAxis.append("text")
      .attr("x", width / 2)
      .attr("y", 40)
      .style("text-anchor", "middle")
      .text("Quarter");

    const yAxis = svg.append("g").call(d3.axisLeft(y));
    yAxis.append("text")
      .attr("transform", "rotate(-90)")
      .attr("x", -height / 2)
      .attr("y", -50)
      .style("text-anchor", "middle")
      .text("Performance Indicators");

    const group = svg.selectAll(".quarter-group")
      .data(data)
      .enter().append("g")
      .attr("class", "quarter-group")
      .attr("transform", d => "translate(" + x(d.Quarter) + ",0)");

    group.selectAll("rect")
      .data(d => categories.map(key => ({{key, value: d[key]}})))
      .enter().append("rect")
      .attr("x", d => xSub(d.key))
      .attr("y", d => y(d.value))
      .attr("height", d => height - y(d.value))
      .attr("width", xSub.bandwidth())
      .attr("fill", d => color(d.key));

    group.selectAll("text.value")
      .data(d => categories.map(key => ({{key, value: d[key]}})))
      .enter().append("text")
      .attr("class", "value")
      .attr("x", d => xSub(d.key) + xSub.bandwidth() / 2)
      .attr("y", d => y(d.value) - 4)
      .attr("text-anchor", "middle")
      .style("font-size", "10px")
      .text(d => d.value);

    const legendLabels = {{"Store_Visits": "Store Visits (Count)", "Electricity_Consumption": "Electricity Consumption (kWh)", "Customer_Comments": "Customer Comments (Count)"}};
    const legend = svg.selectAll(".legend")
      .data(categories)
      .enter().append("g")
      .attr("class", "legend")
      .attr("transform", (d, i) => "translate(" + i * 200 + ",-10)");

    legend.append("rect")
      .attr("x", 0)
      .attr("width", 18)
      .attr("height", 18)
      .style("fill", d => color(d));

    legend.append("text")
      .attr("x", 24)
      .attr("y", 9)
      .attr("dy", ".35em")
      .style("text-anchor", "start")
      .style("font-size", "12px")
      .text(d => legendLabels[d] || d);
  </script>
</body>
</html>"""
    clean_html_path = task_dir / "clean_source.html"
    clean_html_path.write_text(clean_html, encoding="utf-8")
    screenshot_html(clean_html_path, dest)
    return {
        "renderer": "d3_playwright",
        "plot_type": task.get("plot_type"),
        "misleader_type": task.get("misleader_type"),
        "cleaning_rule": "source-like_grouped_bars_for_non_cumulative_metrics",
        "clean_source_html": rel(clean_html_path),
        "grouped_bar_categories": categories,
    }


def render_scale_range_bar_source_chart(task: dict[str, Any], csv_path: Path, dest: Path, task_dir: Path) -> dict[str, Any]:
    df = clean_dataframe(csv_path)
    if "Product" not in df.columns or "Units" not in df.columns:
        raise ValueError(f"{task.get('official_slug')} expected Product and Units columns")
    data = [
        {"Product": str(row["Product"]), "Units": float(row["Units"])}
        for _, row in df.iterrows()
    ]
    source_json = json.dumps(data, ensure_ascii=False)
    title = chart_title(task)
    clean_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(title)}</title>
  <script src="https://d3js.org/d3.v6.min.js"></script>
  <style>
    #chart {{
      width: 1000px;
      height: 750px;
      margin: 60px auto;
    }}
    .bar {{ fill: #8B0000; }}
    .axis path, .axis line {{ stroke: #000; }}
    .axis-label {{ font-size: 14px; font-weight: bold; text-anchor: middle; }}
  </style>
</head>
<body>
  <h1>{html.escape(title)}</h1>
  <div id="chart"></div>
  <script>
    const margin = {{top: 40, right: 30, bottom: 50, left: 80}};
    const width = 1000 - margin.left - margin.right;
    const height = 750 - margin.top - margin.bottom;

    const svg = d3.select("#chart").append("svg")
      .attr("width", width + margin.left + margin.right)
      .attr("height", height + margin.top + margin.bottom);

    const g = svg.append("g").attr("transform", `translate(${{margin.left}},${{margin.top}})`);
    const data = {source_json};

    const x = d3.scaleBand()
      .domain(data.map(d => d.Product))
      .range([0, width])
      .padding(0.2);

    const y = d3.scaleLinear()
      .domain([0, d3.max(data, d => d.Units)])
      .nice()
      .range([height, 0]);

    g.append("g").attr("transform", `translate(0,${{height}})`).call(d3.axisBottom(x));
    g.append("g").call(d3.axisLeft(y).ticks(6).tickFormat(d3.format(",.0f")));

    svg.append("text")
      .attr("class", "axis-label")
      .attr("x", width / 2 + margin.left)
      .attr("y", height + margin.top + 40)
      .text("Product");

    svg.append("text")
      .attr("class", "axis-label")
      .attr("transform", "rotate(-90)")
      .attr("x", -height / 2 - margin.top)
      .attr("y", margin.left - 60)
      .text("Units Sold");

    g.selectAll(".bar")
      .data(data)
      .enter().append("rect")
      .attr("class", "bar")
      .attr("x", d => x(d.Product))
      .attr("y", d => y(d.Units))
      .attr("height", d => height - y(d.Units))
      .attr("width", x.bandwidth());
  </script>
</body>
</html>"""
    clean_html_path = task_dir / "clean_source.html"
    clean_html_path.write_text(clean_html, encoding="utf-8")
    screenshot_html(clean_html_path, dest)
    return {
        "renderer": "d3_playwright",
        "plot_type": task.get("plot_type"),
        "misleader_type": task.get("misleader_type"),
        "cleaning_rule": "source-like_bar_chart_zero_baseline_units",
        "clean_source_html": rel(clean_html_path),
        "bar_value_column": "Units",
        "bar_y_domain_min": 0,
    }


def render_energy_usage_zero_baseline_bar_source_chart(task: dict[str, Any], csv_path: Path, dest: Path, task_dir: Path) -> dict[str, Any]:
    df = clean_dataframe(csv_path)
    if "Month" not in df.columns or "kWh" not in df.columns:
        raise ValueError(f"{task.get('official_slug')} expected Month and kWh columns")
    data = [
        {"Month": str(row["Month"]), "kWh": float(row["kWh"])}
        for _, row in df.iterrows()
    ]
    source_json = json.dumps(data, ensure_ascii=False)
    title = chart_title(task)
    clean_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(title)}</title>
  <script src="https://d3js.org/d3.v6.min.js"></script>
  <style>
    #chart {{
      width: 1000px;
      height: 750px;
      margin: 60px auto;
    }}
    .bar {{ fill: #8B0000; }}
    .axis path, .axis line {{ stroke: #000; }}
    .axis-label {{ font-size: 14px; font-weight: bold; text-anchor: middle; }}
  </style>
</head>
<body>
  <h1>{html.escape(title)}</h1>
  <div id="chart"></div>
  <script>
    const margin = {{top: 40, right: 30, bottom: 50, left: 80}};
    const width = 1000 - margin.left - margin.right;
    const height = 750 - margin.top - margin.bottom;

    const svg = d3.select("#chart").append("svg")
      .attr("width", width + margin.left + margin.right)
      .attr("height", height + margin.top + margin.bottom);

    const g = svg.append("g").attr("transform", `translate(${{margin.left}},${{margin.top}})`);
    const data = {source_json};

    const x = d3.scaleBand()
      .domain(data.map(d => d.Month))
      .range([0, width])
      .padding(0.2);

    const y = d3.scaleLinear()
      .domain([0, d3.max(data, d => d.kWh)])
      .range([height, 0]);

    g.append("g").attr("transform", `translate(0,${{height}})`).call(d3.axisBottom(x));
    g.append("g").call(d3.axisLeft(y).ticks(6).tickFormat(d3.format(",.0f")));

    svg.append("text")
      .attr("class", "axis-label")
      .attr("x", width / 2 + margin.left)
      .attr("y", height + margin.top + 40)
      .text("Month");

    svg.append("text")
      .attr("class", "axis-label")
      .attr("transform", "rotate(-90)")
      .attr("x", -height / 2 - margin.top)
      .attr("y", margin.left - 60)
      .text("Energy Usage (kWh)");

    g.selectAll(".bar")
      .data(data)
      .enter().append("rect")
      .attr("class", "bar")
      .attr("x", d => x(d.Month))
      .attr("y", d => y(d.kWh))
      .attr("height", d => height - y(d.kWh))
      .attr("width", x.bandwidth());
  </script>
</body>
</html>"""
    clean_html_path = task_dir / "clean_source.html"
    clean_html_path.write_text(clean_html, encoding="utf-8")
    screenshot_html(clean_html_path, dest)
    return {
        "renderer": "d3_playwright",
        "plot_type": task.get("plot_type"),
        "misleader_type": task.get("misleader_type"),
        "cleaning_rule": "source-like_bar_chart_zero_baseline_kwh",
        "clean_source_html": rel(clean_html_path),
        "bar_category_column": "Month",
        "bar_value_column": "kWh",
        "bar_y_domain_min": 0,
    }


def render_rewrite_value_zero_baseline_bar_source_chart(task: dict[str, Any], csv_path: Path, dest: Path, task_dir: Path) -> dict[str, Any]:
    df = clean_dataframe(csv_path)
    if "Month" not in df.columns or "value" not in df.columns:
        raise ValueError(f"{task.get('official_slug')} expected Month and value columns")
    metric = str(df["metric"].iloc[0]) if "metric" in df.columns and len(df) else "value"
    data = [
        {"Month": str(row["Month"]), "value": float(row["value"]), "metric": metric}
        for _, row in df.iterrows()
    ]
    source_json = json.dumps(data, ensure_ascii=False)
    title = chart_title(task)
    y_label = metric.replace("_", " ").title()
    clean_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(title)}</title>
  <script src="https://d3js.org/d3.v6.min.js"></script>
  <style>
    #chart {{
      width: 1000px;
      height: 750px;
      margin: 60px auto;
    }}
    .bar {{ fill: #8B0000; }}
    .axis path, .axis line {{ stroke: #000; }}
    .axis-label {{ font-size: 14px; font-weight: bold; text-anchor: middle; }}
  </style>
</head>
<body>
  <h1>{html.escape(title)}</h1>
  <div id="chart"></div>
  <script>
    const margin = {{top: 40, right: 30, bottom: 50, left: 80}};
    const width = 1000 - margin.left - margin.right;
    const height = 750 - margin.top - margin.bottom;

    const svg = d3.select("#chart").append("svg")
      .attr("width", width + margin.left + margin.right)
      .attr("height", height + margin.top + margin.bottom);

    const g = svg.append("g").attr("transform", `translate(${{margin.left}},${{margin.top}})`);
    const data = {source_json};

    const x = d3.scaleBand()
      .domain(data.map(d => d.Month))
      .range([0, width])
      .padding(0.2);

    const y = d3.scaleLinear()
      .domain([0, d3.max(data, d => d.value)])
      .range([height, 0]);

    g.append("g").attr("transform", `translate(0,${{height}})`).call(d3.axisBottom(x));
    g.append("g").call(d3.axisLeft(y).ticks(6).tickFormat(d3.format(",.0f")));

    svg.append("text")
      .attr("class", "axis-label")
      .attr("x", width / 2 + margin.left)
      .attr("y", height + margin.top + 40)
      .text("Month");

    svg.append("text")
      .attr("class", "axis-label")
      .attr("transform", "rotate(-90)")
      .attr("x", -height / 2 - margin.top)
      .attr("y", margin.left - 60)
      .text("{html.escape(y_label)}");

    g.selectAll(".bar")
      .data(data)
      .enter().append("rect")
      .attr("class", "bar")
      .attr("x", d => x(d.Month))
      .attr("y", d => y(d.value))
      .attr("height", d => height - y(d.value))
      .attr("width", x.bandwidth());
  </script>
</body>
</html>"""
    clean_html_path = task_dir / "clean_source.html"
    clean_html_path.write_text(clean_html, encoding="utf-8")
    screenshot_html(clean_html_path, dest)
    return {
        "renderer": "d3_playwright",
        "plot_type": task.get("plot_type"),
        "misleader_type": task.get("misleader_type"),
        "cleaning_rule": "source-like_bar_chart_zero_baseline_value",
        "clean_source_html": rel(clean_html_path),
        "bar_category_column": "Month",
        "bar_value_column": "value",
        "ignored_misleading_column": "axis_start",
        "bar_y_domain_min": 0,
    }


def render_rewrite_average_annotation_bar_source_chart(task: dict[str, Any], csv_path: Path, dest: Path, task_dir: Path) -> dict[str, Any]:
    df = clean_dataframe(csv_path)
    if "month" not in df.columns or "value" not in df.columns:
        raise ValueError(f"{task.get('official_slug')} expected month and value columns")
    data = [
        {"month": str(row["month"]), "value": float(row["value"])}
        for _, row in df.iterrows()
    ]
    if "true_average" in df.columns:
        true_average = float(pd.to_numeric(df["true_average"], errors="coerce").dropna().iloc[0])
    else:
        true_average = sum(item["value"] for item in data) / len(data)
    source_json = json.dumps(data, ensure_ascii=False)
    title = chart_title(task)
    y_labels = {
        "env025": "Alert Days",
        "env026": "Discharge Level Index",
        "env027": "Alert days",
        "env028": "Inflow volume (Mm3)",
    }
    y_label = y_labels.get(task.get("official_slug"), "Value")
    y_max = max(max(item["value"] for item in data), true_average) * 1.18
    ignored_column = "wrong_average_line" if "wrong_average_line" in df.columns else None
    clean_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(title)}</title>
  <script src="https://d3js.org/d3.v7.min.js"></script>
  <style>
    #chart {{
      width: 1000px;
      height: 750px;
      margin: 50px auto;
    }}
    .bar {{ fill: #4f7faf; }}
    .avg-line {{ stroke: black; stroke-dasharray: 7,7; stroke-width: 2px; }}
    .annotation {{ font-size: 18px; font-weight: bold; fill: black; }}
    .axis path, .axis line {{ stroke: #000; }}
    .axis-label {{ font-size: 18px; font-weight: bold; text-anchor: middle; }}
  </style>
</head>
<body>
  <h1 style="text-align: center; font-size: 32px; font-weight: bold;">{html.escape(title)}</h1>
  <div id="chart"></div>
  <script>
    const margin = {{top: 40, right: 80, bottom: 70, left: 80}};
    const width = 1000 - margin.left - margin.right;
    const height = 750 - margin.top - margin.bottom;
    const data = {source_json};
    const trueAverage = {true_average};

    const svg = d3.select("#chart").append("svg")
      .attr("width", width + margin.left + margin.right)
      .attr("height", height + margin.top + margin.bottom);

    const g = svg.append("g").attr("transform", `translate(${{margin.left}},${{margin.top}})`);
    const x = d3.scaleBand()
      .domain(data.map(d => d.month))
      .range([0, width])
      .padding(0.42);
    const y = d3.scaleLinear()
      .domain([0, {y_max}])
      .range([height, 0]);

    g.append("g").attr("transform", `translate(0,${{height}})`).call(d3.axisBottom(x));
    g.append("g").call(d3.axisLeft(y).ticks(6).tickFormat(d3.format(",.0f")));

    svg.append("text")
      .attr("class", "axis-label")
      .attr("x", width / 2 + margin.left)
      .attr("y", height + margin.top + 55)
      .text("Month");

    svg.append("text")
      .attr("class", "axis-label")
      .attr("transform", "rotate(-90)")
      .attr("x", -height / 2 - margin.top)
      .attr("y", margin.left - 55)
      .text("{html.escape(y_label)}");

    g.selectAll(".bar")
      .data(data)
      .enter().append("rect")
      .attr("class", "bar")
      .attr("x", d => x(d.month))
      .attr("y", d => y(d.value))
      .attr("height", d => height - y(d.value))
      .attr("width", x.bandwidth());

    g.append("line")
      .attr("class", "avg-line")
      .attr("x1", 0)
      .attr("y1", y(trueAverage))
      .attr("x2", width)
      .attr("y2", y(trueAverage));

    g.append("text")
      .attr("class", "annotation")
      .attr("x", width - 10)
      .attr("y", y(trueAverage) - 10)
      .attr("text-anchor", "end")
      .text("Average");
  </script>
</body>
</html>"""
    clean_html_path = task_dir / "clean_source.html"
    clean_html_path.write_text(clean_html, encoding="utf-8")
    screenshot_html(clean_html_path, dest)
    info = {
        "renderer": "d3_playwright",
        "plot_type": task.get("plot_type"),
        "misleader_type": task.get("misleader_type"),
        "cleaning_rule": "source-like_bar_chart_true_average_annotation",
        "clean_source_html": rel(clean_html_path),
        "bar_category_column": "month",
        "bar_value_column": "value",
        "true_average": true_average,
    }
    if ignored_column:
        info["ignored_misleading_column"] = ignored_column
    return info


def render_scale_function_pie_source_chart(task: dict[str, Any], csv_path: Path, dest: Path, task_dir: Path) -> dict[str, Any]:
    df = clean_dataframe(csv_path)
    if "brand" not in df.columns or "market_share" not in df.columns:
        raise ValueError(f"{task.get('official_slug')} expected brand and market_share columns")
    data = [
        {"brand": str(row["brand"]), "market_share": float(row["market_share"])}
        for _, row in df.iterrows()
    ]
    title = chart_title(task)
    source_json = json.dumps(data, ensure_ascii=False)
    clean_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(title)}</title>
  <script src="https://d3js.org/d3.v7.min.js"></script>
  <style>
    #chart {{
      width: 1000px;
      height: 750px;
      margin: 60px auto;
    }}
    .label {{
      font-size: 12px;
      font-weight: bold;
      text-anchor: middle;
      fill: white;
    }}
  </style>
</head>
<body>
  <h1>{html.escape(title)}</h1>
  <div id="chart"></div>
  <script>
    const width = 1000;
    const height = 750;
    const radius = Math.min(width, height) / 2;

    const data = {source_json};
    const color = d3.scaleOrdinal()
      .domain(data.map(d => d.brand))
      .range(["#D73027", "#F46D43", "#FDAE61", "#FEE08B", "#E0F3F8", "#ABD9E9", "#74ADD1", "#4575B4"]);

    const svg = d3.select("#chart").append("svg")
      .attr("width", width)
      .attr("height", height)
      .append("g")
      .attr("transform", `translate(${{width / 2}}, ${{height / 2}})`);

    const pie = d3.pie().value(d => +d.market_share);

    const arc = d3.arc()
      .innerRadius(0)
      .outerRadius(radius);

    svg.selectAll("path")
      .data(pie(data))
      .enter().append("path")
      .attr("d", arc)
      .attr("fill", d => color(d.data.brand))
      .attr("stroke", "#fff")
      .style("stroke-width", "1px");

    svg.selectAll("text")
      .data(pie(data))
      .enter().append("text")
      .attr("transform", d => `translate(${{arc.centroid(d)}})`)
      .attr("class", "label")
      .text(d => `${{d.data.brand}} (${{d.data.market_share}}%)`)
      .style("font-size", "16px")
      .style("font-weight", "bold");
  </script>
</body>
</html>"""
    clean_html_path = task_dir / "clean_source.html"
    clean_html_path.write_text(clean_html, encoding="utf-8")
    screenshot_html(clean_html_path, dest)
    return {
        "renderer": "d3_playwright",
        "plot_type": task.get("plot_type"),
        "misleader_type": task.get("misleader_type"),
        "cleaning_rule": "source-like_pie_slices_use_true_market_share",
        "clean_source_html": rel(clean_html_path),
        "pie_value_column": "market_share",
    }


def render_energy_scale_function_pie_source_chart(task: dict[str, Any], csv_path: Path, dest: Path, task_dir: Path) -> dict[str, Any]:
    df = clean_dataframe(csv_path)
    required = {"energy_source", "consumption_percentage"}
    if not required.issubset(df.columns):
        raise ValueError(f"{task.get('official_slug')} expected energy_source and consumption_percentage columns")
    data = [
        {"energy_source": str(row["energy_source"]), "consumption_percentage": float(row["consumption_percentage"])}
        for _, row in df.iterrows()
    ]
    title = chart_title(task)
    source_json = json.dumps(data, ensure_ascii=False)
    clean_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(title)}</title>
  <script src="https://d3js.org/d3.v7.min.js"></script>
  <style>
    #chart {{
      width: 1000px;
      height: 750px;
      margin: 60px auto;
    }}
    .label {{
      font-size: 12px;
      font-weight: bold;
      text-anchor: middle;
      fill: white;
    }}
  </style>
</head>
<body>
  <h1>{html.escape(title)}</h1>
  <div id="chart"></div>
  <script>
    const width = 1000;
    const height = 750;
    const radius = Math.min(width, height) / 2;

    const data = {source_json};
    const color = d3.scaleOrdinal()
      .domain(["Fossil Fuels", "Hydroelectric", "Renewables", "Nuclear"])
      .range(["#D73027", "#F46D43", "#FDAE61", "#FEE08B", "#E0F3F8", "#ABD9E9", "#74ADD1", "#4575B4"]);

    const svg = d3.select("#chart").append("svg")
      .attr("width", width)
      .attr("height", height)
      .append("g")
      .attr("transform", `translate(${{width / 2}}, ${{height / 2}})`);

    const pie = d3.pie().value(d => +d.consumption_percentage);

    const arc = d3.arc()
      .innerRadius(0)
      .outerRadius(radius);

    svg.selectAll("path")
      .data(pie(data))
      .enter().append("path")
      .attr("d", arc)
      .attr("fill", d => color(d.data.energy_source))
      .attr("stroke", "#fff")
      .style("stroke-width", "1px");

    svg.selectAll("text")
      .data(pie(data))
      .enter().append("text")
      .attr("transform", d => `translate(${{arc.centroid(d)}})`)
      .attr("class", "label")
      .text(d => `${{d.data.energy_source}} (${{d.data.consumption_percentage}}%)`)
      .style("font-size", "16px")
      .style("font-weight", "bold");
  </script>
</body>
</html>"""
    clean_html_path = task_dir / "clean_source.html"
    clean_html_path.write_text(clean_html, encoding="utf-8")
    screenshot_html(clean_html_path, dest)
    return {
        "renderer": "d3_playwright",
        "plot_type": task.get("plot_type"),
        "misleader_type": task.get("misleader_type"),
        "cleaning_rule": "source-like_pie_slices_use_true_consumption_percentage",
        "clean_source_html": rel(clean_html_path),
        "pie_entity_column": "energy_source",
        "pie_value_column": "consumption_percentage",
        "ignored_misleading_column": "adjusted_scale",
    }


def screenshot_html(html_path: Path, dest: Path) -> None:
    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            return

    handler = lambda *args, **kwargs: QuietHandler(*args, directory=str(OUT_DIR), **kwargs)
    with socketserver.TCPServer(("127.0.0.1", 0), handler) as httpd:
        port = httpd.server_address[1]
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{port}/{html_path.relative_to(OUT_DIR).as_posix()}"
            last_error: Exception | None = None
            for _attempt in range(3):
                try:
                    with sync_playwright() as playwright:
                        browser = playwright.chromium.launch(headless=True)
                        page = browser.new_page(viewport={"width": 1120, "height": 840}, device_scale_factor=1)
                        page.goto(url, wait_until="domcontentloaded", timeout=60000)
                        page.locator("svg").wait_for(state="visible", timeout=60000)
                        page.wait_for_function(
                            """() => {
                                const svg = document.querySelector('svg');
                                if (!svg) return false;
                                return svg.querySelectorAll('path, rect, circle, line, text').length > 5;
                            }""",
                            timeout=60000,
                        )
                        page.wait_for_timeout(1000)
                        page.screenshot(path=str(dest), full_page=True)
                        browser.close()
                    return
                except Exception as exc:
                    last_error = exc
                    try:
                        browser.close()
                    except Exception:
                        pass
            raise RuntimeError(f"Failed to screenshot {html_path}") from last_error
        finally:
            httpd.shutdown()
            thread.join(timeout=2)


def render_choropleth_tile_map(task: dict[str, Any], df: pd.DataFrame, dest: Path) -> None:
    numeric_cols = true_numeric_columns(df)
    if not numeric_cols:
        save_no_data_chart(task, dest, "No numeric value column was available.")
        return
    value_col = numeric_cols[0]
    label_col = None
    for candidate in ["abbr", "State", "state"]:
        if candidate in df.columns:
            label_col = candidate
            break
    if label_col is None:
        label_col = df.columns[0]
    labels = df[label_col].astype(str).str.upper().tolist()
    values = pd.to_numeric(df[value_col], errors="coerce")
    fig, ax = plt.subplots(figsize=(10.5, 7.5), dpi=140)
    cmap = plt.cm.YlOrRd
    norm = plt.Normalize(vmin=float(values.min()), vmax=float(values.max()))
    used_tile = 0
    for idx, (label, value) in enumerate(zip(labels, values)):
        abbr = label[:2].upper()
        x, y = STATE_TILE_POSITIONS.get(abbr, (idx % 12, 8 + idx // 12))
        color = cmap(norm(float(value))) if pd.notna(value) else "#dddddd"
        rect = plt.Rectangle((x, -y), 0.92, 0.92, facecolor=color, edgecolor="white", linewidth=1.2)
        ax.add_patch(rect)
        ax.text(x + 0.46, -y + 0.55, label if len(label) <= 3 else label[:2], ha="center", va="center", fontsize=8, weight="bold")
        ax.text(x + 0.46, -y + 0.25, f"{value:g}" if pd.notna(value) else "", ha="center", va="center", fontsize=6.5)
        used_tile += 1
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, fraction=0.035, pad=0.02)
    cbar.set_label(value_col)
    ax.set_xlim(-0.2, 12.4)
    ax.set_ylim(-9.3, 0.8)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(chart_title(task), fontsize=16, pad=16)
    ax.text(0, -9.15, "Clean tile-map rendering: darker color means higher true value.", fontsize=10, color="#4b5563")
    fig.tight_layout()
    fig.savefig(dest, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def write_clean_source_html(task: dict[str, Any], task_dir: Path, entry: dict[str, Any]) -> str:
    rule = entry.get("cleaning_rule") or entry.get("clean_source_type") or "faithful_clean_pair"
    payload = {
        "official_slug": task.get("official_slug"),
        "task_id": task.get("task_id"),
        "case_id": task.get("case_id"),
        "misleader_type": task.get("misleader_type"),
        "plot_type": task.get("plot_type"),
        "cleaning_rule": rule,
        "ground_truth": task.get("ground_truth"),
        "misleading_context": task.get("misleading_context"),
    }
    html_text = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(task.get('official_slug') or 'task')} clean chart source</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #111827; }}
    img {{ max-width: 100%; border: 1px solid #d1d5db; }}
    pre {{ white-space: pre-wrap; background: #f3f4f6; padding: 12px; border-radius: 6px; }}
  </style>
</head>
<body>
  <h1>{html.escape(chart_title(task))}</h1>
  <p>This is the clean-pair rendering for <strong>{html.escape(task.get('official_slug') or '')}</strong>. The chart uses the official task CSV and removes the misleading visual mechanism while leaving task semantics unchanged.</p>
  <p><strong>Cleaning rule:</strong> {html.escape(str(rule))}</p>
  <img src="clean.png" alt="Clean chart">
  <h2>Source metadata</h2>
  <pre>{html.escape(json.dumps(payload, ensure_ascii=False, indent=2))}</pre>
</body>
</html>
"""
    dest = task_dir / "clean_source.html"
    dest.write_text(html_text, encoding="utf-8")
    return rel(dest) or "clean_source.html"


def process_task(task: dict[str, Any], index: int) -> dict[str, Any]:
    slug = task.get("official_slug") or f"task_{index:03d}"
    task_dir = OUT_DIR / "tasks" / f"{index:03d}_{safe_name(slug)}"
    task_dir.mkdir(parents=True, exist_ok=True)
    chart = task.get("chart_asset") or {}

    figure_src = Path(chart["figure_path"]) if chart.get("figure_path") else None
    if not figure_src or not figure_src.exists():
        raise FileNotFoundError(f"Missing misleading figure for {slug}: {figure_src}")
    misleading_dest = task_dir / f"misleading{figure_src.suffix or '.png'}"
    misleading_rel = copy_file(figure_src, misleading_dest)

    csv_src = Path(chart["csv_path"]) if chart.get("csv_path") else None
    source_csv_rel = copy_file(csv_src, task_dir / "source.csv") if csv_src and csv_src.exists() else None

    source_html = resolve_mcqa_html(task) if is_mcqa_series(task) else None
    source_html_rel = copy_file(source_html, task_dir / "source_misleading.html") if source_html else None

    clean_dest = task_dir / "clean.png"
    entry: dict[str, Any] = {
        "index": index,
        "official_slug": slug,
        "task_id": task.get("task_id"),
        "case_id": task.get("case_id"),
        "official_scenario": task.get("official_scenario"),
        "source_dataset": "visDeception" if is_visdeception(task) else "MisleadingChartQA",
        "misleader_type": task.get("misleader_type"),
        "plot_type": task.get("plot_type"),
        "task_dir": rel(task_dir),
        "misleading_image": misleading_rel,
        "clean_image": rel(clean_dest),
        "source_csv": source_csv_rel,
        "source_misleading_html": source_html_rel,
        "original_chart_asset": chart,
        "workflow_instruction": task.get("workflow_instruction"),
        "ground_truth": task.get("ground_truth"),
        "intermediate_decision": task.get("intermediate_decision"),
        "misleading_context": task.get("misleading_context"),
        "action_space": task.get("action_space"),
    }

    if is_visdeception(task):
        paired = paired_visdeception_clean_path(figure_src)
        if not paired:
            raise FileNotFoundError(f"Missing visDeception paired clean image for {slug}: {figure_src}")
        shutil.copy2(paired, clean_dest)
        entry["clean_source_type"] = "visDeception official paired Control/regular image"
        entry["paired_clean_source_path"] = str(paired)
    else:
        if not csv_src or not csv_src.exists():
            raise FileNotFoundError(f"Missing CSV for MCQA-series task {slug}: {csv_src}")
        if task.get("plot_type") == "choropleth_map":
            render_info = render_choropleth_source_map(task, csv_src, clean_dest, task_dir)
        elif task.get("official_slug") in {"pub008", "pub009"}:
            render_info = render_stacked_bar_source_chart(task, csv_src, clean_dest, task_dir)
        elif task.get("official_slug") == "pub010":
            render_info = render_pub010_line_source_chart(task, csv_src, clean_dest, task_dir)
        elif task.get("official_slug") in {"pub011", "pub023"}:
            render_info = render_pub011_bar_source_chart(task, csv_src, clean_dest, task_dir)
        elif task.get("official_slug") in {"pub020", "pub021", "pub022", "b003", "b006", "b008"}:
            render_info = render_data_visual_disproportion_scatter_source_chart(task, csv_src, clean_dest, task_dir)
        elif task.get("official_slug") in {
            "b017", "b018", "b019", "b020", "b021", "b022", "b023", "b024", "b025", "b026", "b027", "b028", "b029", "b030", "b031", "b032", "b033", "b034"
        }:
            render_info = render_cherry_picking_scatter_source_chart(task, csv_src, clean_dest, task_dir)
        elif task.get("official_slug") in {"health006", "health007", "health008", "health009"}:
            render_info = render_health_cherry_picking_line_source_chart(task, csv_src, clean_dest, task_dir)
        elif task.get("official_slug") in {"health010", "health011", "health012", "health013"}:
            render_info = render_health_scatter_cherry_picking_source_chart(task, csv_src, clean_dest, task_dir)
        elif task.get("official_slug") in {"health016", "health017", "health018", "health019"}:
            render_info = render_health_trend_title_line_source_chart(task, csv_src, clean_dest, task_dir)
        elif task.get("official_slug") in {"b002", "b005", "b007", "b010"}:
            render_info = render_data_visual_disproportion_bar_source_chart(task, csv_src, clean_dest, task_dir)
        elif task.get("official_slug") == "env008":
            render_info = render_energy_production_bar_source_chart(task, csv_src, clean_dest, task_dir)
        elif task.get("official_slug") in {"env021", "env022", "env023", "env024"}:
            render_info = render_rewrite_reported_percentage_bar_source_chart(task, csv_src, clean_dest, task_dir)
        elif task.get("official_slug") in {"pub024", "pub025", "pub026", "pub027", "pub028", "pub029", "b035", "b036", "b037", "b038", "b039", "b040"}:
            render_info = render_misleading_annotation_line_source_chart(task, csv_src, clean_dest, task_dir)
        elif task.get("official_slug") in {"env029", "env030", "env031"}:
            render_info = render_rewrite_neutral_title_line_source_chart(task, csv_src, clean_dest, task_dir)
        elif task.get("official_slug") in {"b041", "b042", "b043", "b044", "b045", "b046", "b047"}:
            render_info = render_misleading_annotation_bar_source_chart(task, csv_src, clean_dest, task_dir)
        elif task.get("official_slug") in {"env025", "env026", "env027", "env028"}:
            render_info = render_rewrite_average_annotation_bar_source_chart(task, csv_src, clean_dest, task_dir)
        elif task.get("official_slug") == "pub030":
            render_info = render_pub030_pie_source_chart(task, csv_src, clean_dest, task_dir)
        elif task.get("official_slug") in {"env003", "env004", "env005", "env006"}:
            render_info = render_energy_scale_function_pie_source_chart(task, csv_src, clean_dest, task_dir)
        elif task.get("official_slug") in {"b001", "b004", "b009"}:
            render_info = render_scale_function_pie_source_chart(task, csv_src, clean_dest, task_dir)
        elif task.get("official_slug") == "b011":
            render_info = render_cumulative_grouped_bar_source_chart(task, csv_src, clean_dest, task_dir)
        elif task.get("official_slug") == "env007":
            render_info = render_energy_usage_zero_baseline_bar_source_chart(task, csv_src, clean_dest, task_dir)
        elif task.get("official_slug") in {"env017", "env018", "env019", "env020"}:
            render_info = render_rewrite_value_zero_baseline_bar_source_chart(task, csv_src, clean_dest, task_dir)
        elif task.get("official_slug") in {"b012", "b013", "b014", "b015", "b016"}:
            render_info = render_scale_range_bar_source_chart(task, csv_src, clean_dest, task_dir)
        else:
            render_info = render_clean_chart(task, csv_src, clean_dest)
        entry.update(render_info)
    if not entry.get("clean_source_html"):
        entry["clean_source_html"] = write_clean_source_html(task, task_dir, entry)

    task_json = task_dir / "task.json"
    task_json.write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8")
    entry["task_json"] = rel(task_json)
    if source_csv_rel:
        entry["csv_rows"] = read_csv_rows(task_dir / "source.csv")
    return entry


def write_manifest(entries: list[dict[str, Any]]) -> None:
    meta = {
        "dataset": "clean_datasets",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_official_dir": str(OFFICIAL_DIR),
        "task_count": len(entries),
        "scenario_counts": {
            scenario: sum(1 for entry in entries if entry.get("official_scenario") == scenario)
            for scenario, _ in SCENARIO_TASK_FILES
        },
        "source_dataset_counts": {
            "MisleadingChartQA": sum(1 for entry in entries if entry.get("source_dataset") == "MisleadingChartQA"),
            "visDeception": sum(1 for entry in entries if entry.get("source_dataset") == "visDeception"),
        },
    }
    (OUT_DIR / "manifest.json").write_text(
        json.dumps({"meta": meta, "tasks": entries}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_jsonl(OUT_DIR / "manifest.jsonl", entries)
    data_dir = OUT_DIR / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    js = "window.CLEAN_DATASET_META = " + json.dumps(meta, ensure_ascii=False, indent=2)
    js += ";\nwindow.CLEAN_DATASET_TASKS = " + json.dumps(entries, ensure_ascii=False, indent=2) + ";\n"
    (data_dir / "manifest.js").write_text(js, encoding="utf-8")


def write_index_html() -> None:
    html_text = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Clean Datasets Review</title>
  <style>
    :root { --line:#d8dee8; --text:#17202a; --muted:#5e6b78; --accent:#176b87; }
    * { box-sizing: border-box; }
    body { margin: 0; font-family: Arial, sans-serif; color: var(--text); background:#f6f7f9; }
    .layout { display:grid; grid-template-columns:330px 1fr; min-height:100vh; }
    aside { background:white; border-right:1px solid var(--line); height:100vh; position:sticky; top:0; display:flex; flex-direction:column; }
    .head,.filters { padding:14px 16px; border-bottom:1px solid var(--line); }
    h1 { font-size:18px; margin:0 0 6px; }
    input,select,textarea,button { font:inherit; }
    input,select,textarea { width:100%; padding:8px; border:1px solid var(--line); border-radius:6px; margin-top:8px; }
    .list { overflow:auto; padding:8px; }
    .row { display:block; width:100%; text-align:left; border:1px solid transparent; background:transparent; border-radius:6px; padding:9px; margin-bottom:4px; cursor:pointer; }
    .row.active { border-color:#a8cdd6; background:#eaf3f4; }
    .row small { display:block; color:var(--muted); margin-top:3px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    main { min-width:0; }
    .top { background:#f6f7f9; border-bottom:1px solid var(--line); padding:14px 20px; position:sticky; top:0; z-index:2; display:flex; justify-content:space-between; gap:10px; }
    .content { padding:20px; display:grid; grid-template-columns:1fr 1fr; gap:16px; align-items:start; }
    section { background:white; border:1px solid var(--line); border-radius:8px; padding:14px; min-width:0; }
    img { max-width:100%; height:auto; display:block; border:1px solid var(--line); background:white; }
    .pair { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
    h2 { font-size:15px; margin:0 0 10px; }
    h3 { font-size:13px; color:var(--muted); text-transform:uppercase; margin:16px 0 8px; }
    .muted { color:var(--muted); font-size:13px; }
    .block { border-left:3px solid var(--line); padding-left:10px; white-space:pre-wrap; line-height:1.45; }
    a { color:var(--accent); text-decoration:none; }
    pre { white-space:pre-wrap; background:#f3f4f6; border-radius:6px; padding:10px; max-height:300px; overflow:auto; }
    @media(max-width:1050px){ .layout{grid-template-columns:1fr}.content,.pair{grid-template-columns:1fr} aside{position:relative;height:auto;max-height:45vh} }
  </style>
</head>
<body>
  <div class="layout">
    <aside>
      <div class="head"><h1>Clean Datasets Review</h1><div class="muted" id="stats"></div></div>
      <div class="filters"><input id="search" type="search" placeholder="Search slug, case, scenario"><select id="scenario"><option value="">All scenarios</option></select></div>
      <div class="list" id="list"></div>
    </aside>
    <main>
      <div class="top"><div><strong id="title"></strong><div class="muted" id="subtitle"></div></div><div><button id="prev">Prev</button> <button id="next">Next</button></div></div>
      <div class="content" id="content"></div>
    </main>
  </div>
  <script src="data/manifest.js"></script>
  <script>
    const tasks = window.CLEAN_DATASET_TASKS || [];
    const meta = window.CLEAN_DATASET_META || {};
    let filtered = tasks.slice();
    let index = 0;
    const $ = id => document.getElementById(id);
    const esc = v => String(v ?? "").replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    function init() {
      $("stats").textContent = `${meta.task_count || tasks.length} tasks · ${JSON.stringify(meta.source_dataset_counts || {})}`;
      [...new Set(tasks.map(t => t.official_scenario).filter(Boolean))].forEach(s => {
        const o = document.createElement("option"); o.value=s; o.textContent=s; $("scenario").appendChild(o);
      });
      $("search").addEventListener("input", filter);
      $("scenario").addEventListener("change", filter);
      $("prev").addEventListener("click", () => move(-1));
      $("next").addEventListener("click", () => move(1));
      filter();
    }
    function filter() {
      const q = $("search").value.toLowerCase().trim();
      const s = $("scenario").value;
      filtered = tasks.filter(t => (!s || t.official_scenario === s) && (!q || [t.official_slug,t.case_id,t.task_id,t.misleader_type,t.plot_type].join(" ").toLowerCase().includes(q)));
      if (!filtered.includes(tasks[index])) index = tasks.indexOf(filtered[0] || tasks[0]);
      renderList(); render();
    }
    function renderList() {
      $("list").innerHTML = filtered.map(t => `<button class="row ${tasks[index]===t?'active':''}" data-i="${tasks.indexOf(t)}">${String(t.index).padStart(3,'0')} ${esc(t.official_slug)}<small>${esc(t.official_scenario)} · ${esc(t.plot_type)} · ${esc(t.misleader_type)}</small></button>`).join("");
      $("list").onclick = e => { const r=e.target.closest(".row"); if (r) { index=Number(r.dataset.i); renderList(); render(); } };
    }
    function render() {
      const t = tasks[index]; if (!t) return;
      $("title").textContent = `${String(t.index).padStart(3,'0')} / ${tasks.length} · ${t.official_slug}`;
      $("subtitle").textContent = `${t.official_scenario} · ${t.case_id}`;
      const correct = t.intermediate_decision?.correct_value || t.ground_truth?.ground_truth_entity || "";
      const trap = t.intermediate_decision?.misleading_value || t.misleading_context?.misleading_target || "";
      $("content").innerHTML = `
        <section style="grid-column:1/-1"><div class="pair"><div><h2>Misleading</h2><img src="${esc(t.misleading_image)}"></div><div><h2>Clean Pair</h2><img src="${esc(t.clean_image)}"></div></div></section>
        <section><h2>Task</h2><div class="muted">${esc(t.source_dataset)} · ${esc(t.plot_type)} · ${esc(t.misleader_type)}</div><h3>Workflow</h3><div class="block">${esc(t.workflow_instruction)}</div><h3>Correct / Trap</h3><div class="block">Correct: ${esc(correct)}\nTrap: ${esc(trap)}</div><h3>Links</h3><p><a href="${esc(t.clean_source_html)}" target="_blank">clean_source.html</a> · ${t.source_csv ? `<a href="${esc(t.source_csv)}" target="_blank">source.csv</a>` : 'no csv'} · ${t.source_misleading_html ? `<a href="${esc(t.source_misleading_html)}" target="_blank">source_misleading.html</a>` : 'no source html'}</p></section>
        <section><h2>Metadata</h2><h3>Ground Truth</h3><div class="block">${esc(t.ground_truth?.ground_truth_computation || "")}</div><h3>Visual Trap</h3><div class="block">${esc(t.misleading_context?.expected_visual_trap || t.misleading_context?.misleading_mechanism || "")}</div><details><summary>Manifest entry</summary><pre>${esc(JSON.stringify(t, null, 2))}</pre></details></section>`;
      const pos = filtered.indexOf(t);
      $("prev").disabled = pos <= 0;
      $("next").disabled = pos >= filtered.length - 1;
    }
    function move(d) {
      const pos = filtered.indexOf(tasks[index]);
      const next = Math.max(0, Math.min(filtered.length - 1, pos + d));
      index = tasks.indexOf(filtered[next]);
      renderList(); render();
    }
    init();
  </script>
</body>
</html>
"""
    (OUT_DIR / "index.html").write_text(html_text, encoding="utf-8")


def write_readme(entries: list[dict[str, Any]]) -> None:
    readme = f"""# clean_datasets

Generated from `web_agent_benchmark/official_benchmark_v1`.

- Tasks: {len(entries)}
- MisleadingChartQA-series clean charts: {sum(1 for e in entries if e.get('source_dataset') == 'MisleadingChartQA')}
- visDeception official paired clean charts: {sum(1 for e in entries if e.get('source_dataset') == 'visDeception')}

Open `index.html` to review each misleading/clean pair.
"""
    (OUT_DIR / "README.md").write_text(readme, encoding="utf-8")


def validate(entries: list[dict[str, Any]]) -> None:
    if len(entries) != 140:
        raise AssertionError(f"Expected 140 entries, found {len(entries)}")
    mcqa = sum(1 for entry in entries if entry.get("source_dataset") == "MisleadingChartQA")
    vis = sum(1 for entry in entries if entry.get("source_dataset") == "visDeception")
    if mcqa != 120 or vis != 20:
        raise AssertionError(f"Expected 120 MCQA and 20 visDeception entries, found {mcqa} and {vis}")
    missing: list[str] = []
    for entry in entries:
        for key in ["misleading_image", "clean_image", "task_json", "clean_source_html"]:
            path = OUT_DIR / str(entry.get(key))
            if not path.exists() or (key.endswith("image") and path.stat().st_size < 1000):
                missing.append(f"{entry.get('official_slug')}:{key}:{path}")
        if entry.get("source_dataset") == "MisleadingChartQA" and not entry.get("source_csv"):
            missing.append(f"{entry.get('official_slug')}:source_csv")
        if entry.get("source_dataset") == "visDeception" and not entry.get("paired_clean_source_path"):
            missing.append(f"{entry.get('official_slug')}:paired_clean_source_path")
    if missing:
        raise AssertionError("Validation failed:\n" + "\n".join(missing[:50]))


def main() -> None:
    prepare_output()
    copy_official_reference_files()
    tasks: list[dict[str, Any]] = []
    for _, filename in SCENARIO_TASK_FILES:
        tasks.extend(read_jsonl(OFFICIAL_DIR / filename))
    if len(tasks) != 140:
        raise AssertionError(f"Expected 140 official tasks, found {len(tasks)}")
    entries = [process_task(task, index) for index, task in enumerate(tasks, start=1)]
    validate(entries)
    write_manifest(entries)
    write_index_html()
    write_readme(entries)
    print(f"Wrote {OUT_DIR}")
    print(f"Tasks: {len(entries)}")
    print(f"MisleadingChartQA: {sum(1 for entry in entries if entry.get('source_dataset') == 'MisleadingChartQA')}")
    print(f"visDeception: {sum(1 for entry in entries if entry.get('source_dataset') == 'visDeception')}")


if __name__ == "__main__":
    main()
