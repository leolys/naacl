# Offline checks

2026-09-06; reference `stage2_live_smoke_20260906T1342Z` only.

`audit_assets.py` exited 0 using the pre-existing `misleading_webagent_eval` interpreter. Primary release rows and their source-task matches were read without launching a model/browser/GPU. Its stdout is preserved in `primary_asset_audit.json`.

JSON consistency check exited 0. It checked: 7 selected slugs equal the proposed primary list in both files; selected tasks have no differences in the existing runner's 14 pair fields; template-group member partitions are disjoint; image-only drafts are excluded from the primary list.

Exact output:

```text
PASS: 7 selected primary assets; 15 inspected pairs; 14-field pair equality; group partitions disjoint; drafts excluded; 0 model calls / 0 browser transitions.
```

These are metadata/manifest consistency checks. They do not establish visual semantics by themselves, runnable task status, native model image transport, correct natural decisions, successful executor mapping, or successful submission. Visual findings are separately documented after direct `view_image` inspection in `candidate_qualification.md`.
