# Private collaboration handoff

- Preserve original task rows, charts, gold, versioned prompts and historical results.
- Keep the repository private. Public release and third-party permissions require the owner's decision.
- Never put gold, mechanism labels, other-arm content or hidden tables into evaluated model input.
- New experiments need a new output directory, explicit model/resource authorization and a budget. Historical permissions do not carry forward automatically.
- No API keys, SSH keys, cookies, personal account settings, model weights or virtual environments belong here.
- Historical snapshots may contain intentionally unavailable old paths or omitted infrastructure. Use `handoff/SOURCE_PROVENANCE.json` for export identity; do not rewrite old manifests as if they described a new run.
- Start with `README.md`, `docs/HANDOFF_GUIDE_ZH.md`, `environments/README.md` and the offline tools in `tools/`.
- Project-local ARIS research skills are not bundled and remain paused by the owner's request. Do not infer permission to install or enable them from this handoff.

