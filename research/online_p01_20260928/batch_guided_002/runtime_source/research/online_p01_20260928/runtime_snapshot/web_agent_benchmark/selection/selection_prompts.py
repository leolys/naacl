"""Prompts for GPT-assisted MisleadingChartQA case selection."""

SYSTEM_PROMPT = """You are selecting chart cases for a web-agent benchmark.

The benchmark studies whether misleading visualizations cause a web agent to make
the wrong downstream web action. A good case must satisfy all of these:
1. The chart/data semantics clearly fit the requested scenario.
2. The misleading visualization type could plausibly make an agent choose the
   wrong entity or priority.
3. The chart can support a two-stage web workflow: inspect dashboard evidence,
   then choose/search/flag/configure an entity in a later web page.
4. The correct entity must be computable from the CSV using one entity column,
   one metric column, and max/min.

Return strict JSON only. Do not include markdown.
"""

USER_PROMPT_TEMPLATE = """Evaluate this candidate for the scenario "{scenario}".

Allowed scenarios:
- business_operations
- public_statistics
- education_hr
- health_environment

Candidate:
{candidate_json}

Return this JSON object exactly:
{{
  "scenario_fit_score": 1,
  "misleading_strength_score": 1,
  "workflow_suitability_score": 1,
  "semantic_scene": "{scenario}",
  "entity_column": "",
  "metric_column": "",
  "decision_rule": "max",
  "recommended_action_type": "",
  "risk_description": "",
  "keep": false
}}

Scoring guide:
- 5 means excellent, direct, and clean.
- 3 means usable but less direct.
- 1 means weak or unsuitable.

Use "min" only when lower values naturally indicate the target entity, such as
lowest score, lowest satisfaction, or lowest productivity. Otherwise use "max".
For public_statistics, avoid partisan political action framing; choose neutral
review, briefing, or data-quality actions.
"""
