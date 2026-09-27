# Profile Mark-Policy Schema

This document defines the draft profile-side schema used to encode what kinds
of mark/channel changes are allowed for each active taxonomy class.

The four profile fields are:

- `allowed_mark_changes`
- `protected_channels`
- `allowed_scope_changes`
- `invalid_if`

These fields are intentionally machine-friendly. They are not yet a complete
validator implementation, but they are designed so `validator.py`,
`reverse_agent.py`, and `llm_judge.py` can consume them in later patches.

## Core Concepts

- `mark`: the graphical primitive that directly encodes data.
  Examples: bars, points, line segments, bubbles, pie slices.
- `primary_mark_geometry`: the main spatial/size geometry of those marks.
  Examples: bar height, point coordinates, line path, slice angle.
- `non_target_channels`: channels not meant to be changed by the current error
  type. Examples: bubble size when only x/y discretization is intended, or x/y
  positions when only legend ambiguity is intended.
- `retained_scope_values` / `retained_scope_geometry`: for subset/omission
  classes, values and geometry that remain visible after the permitted scope
  reduction.

## Field Semantics

### `allowed_mark_changes`
What kinds of mark or encoding changes are allowed for the category.

Current vocabulary:

- `reference_system_removal_only`
- `title_caption_text_only`
- `reference_text_only`
- `in_chart_label_text_only`
- `legend_binding_presentation_only`
- `layout_order_only`
- `grouping_structure_only`
- `chart_type_remap_only`
- `color_discriminability_only`
- `color_mapping_only`
- `text_readability_only`
- `overlap_or_occlusion_only`
- `encoding_transform_only`
- `axis_mapping_transform_only`
- `aspect_ratio_only`
- `line_style_transform_only`
- `subset_selection_only`
- `context_omission_only`
- `normalization_context_omission_only`
- `uncertainty_visibility_only`
- `chart_level_framing_only`

### `protected_channels`
Channels or invariants that must remain faithful under this category.

Current vocabulary:

- `entity_identity`
- `entity_count`
- `raw_values`
- `primary_mark_geometry`
- `rank_order`
- `non_target_channels`
- `retained_scope_values`
- `retained_scope_geometry`

### `allowed_scope_changes`
What kinds of scope/context changes are allowed.

Current vocabulary:

- `none`
- `display_relayout_without_subset_change`
- `subset_selection`
- `context_omission`
- `normalization_context_omission`
- `uncertainty_context_suppression`
- `chart_level_framing_only`

### `invalid_if`
Conditions that should cause rejection even if the sample appears to match the
headline category.

Current vocabulary:

- `recreates_new_dataset`
- `fabricates_values`
- `changes_entity_identity_or_count`
- `adds_secondary_dominant_mechanism`
- `changes_primary_geometry_without_profile_permission`
- `changes_non_target_channels`
- `changes_scope_without_profile_permission`
- `breaks_rank_order_without_profile_permission`
- `regroups_values_without_traceable_aggregation`
- `changes_chart_type_and_rewrites_values`
- `breaks_retained_scope_truthfulness`
- `uses_explicit_disclosure_text_when_subtlety_required`
- `suppresses_required_uncertainty_with_value_changes`
- `relabels_discrete_bands_inconsistently_with_original_order`

## Design Intent By Major Pattern

### Reference-removal classes
Examples:

- `missingaxis`
- `missingaxisticks`
- `missingaxistitle`
- `missinglegend`
- `missingunits`
- `missingvaluelabels`

These should generally preserve:

- `entity_identity`
- `entity_count`
- `raw_values`
- `primary_mark_geometry`
- `non_target_channels`

### Encoding-transform classes
Examples:

- `discretizedcontinuousvariable`
- `areaencoding` (including pictorial/icon variants)
- `misusingcircularlayout`
- `3d`

These may change how values are encoded visually, but should usually preserve:

- `entity_identity`
- `entity_count`
- `raw_values`
- `rank_order`
- `non_target_channels`

### Axis-mapping classes
Examples:

- `truncatedaxis`
- `extendedaxis`
- `invertedaxis`
- `changingscale`
- `inconsistentticklabels`
- `dualaxis`

These may change apparent mark geometry as part of the target mechanism, but
should still preserve:

- `entity_identity`
- `entity_count`
- `raw_values`
- `rank_order`
- `non_target_channels`

### Scope-manipulation classes
Examples:

- `Cherry_Picking`
- `Missing_Data`
- `Missing_Normalization`

These may alter scope or supporting context, but the retained visible scope
must stay truthful.

## Important Implementation Note

These profile fields are currently a configuration draft. They are intended to
become hard constraints in:

- `reverse_agent.py`
- `validator.py`
- `llm_judge.py`

For now, they should be treated as the canonical design source for future
pipeline tightening.
