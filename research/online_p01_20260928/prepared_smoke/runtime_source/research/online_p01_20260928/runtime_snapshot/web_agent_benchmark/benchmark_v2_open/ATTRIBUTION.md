
# Attribution

This release candidate aggregates task assets and metadata derived from internal benchmark construction artifacts.

## Source Components

- Synthetic paired tasks: `web_agent_benchmark/official_benchmark_v1` and `web_agent_benchmark/clean_benchmark_v1`.
- Real-world extension: `web_agent_benchmark/real_world40_v2_final`.
- Real-world source image URLs are preserved in task-level `chart_asset.source_image_url` fields when available.

## Third-Party Sources To Review Before Public Release

- MisleadingChartQA-derived chart figures/data used by the synthetic benchmark component.
- Bad-Vis-Browser / real-world misleading visualization images referenced by Real-World40.

Before publishing externally, confirm that redistribution of all included assets is permitted under the intended dataset license.
