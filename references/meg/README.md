# Microsoft Azure Migration Execution Guide (MEG) Reference

This directory contains the normalized, pinned machine-readable reference artifacts derived from the official **Microsoft Azure Migration Execution Guide**:
- **Source Repository**: `https://github.com/Azure/migration`
- **Pinned Commit SHA**: `09b269375dc7c48cee7541e4ca16faf02b3897ca`
- **License**: MIT License (see `THIRD_PARTY_NOTICES.md` for full license text)
- **Attribution**: *Aligned with the Microsoft Azure Migration Execution Guide reference*

---

## Artifact Index

| File | Purpose |
|---|---|
| `metadata.json` | Pinned repository, commit SHA, artifact hash, and schema version |
| `lifecycle.json` | 6 migration lifecycle phases (Strategy, Plan, Ready, Adopt, Govern, Manage) and Landfall stage mappings |
| `checklist.json` | 21 readiness criteria across the 15 categories with deterministic evaluation keys |
| `roles.json` | Standard functional migration roles and default RACI/DACI assignment baseline |
| `risks.json` | Risk taxonomy, rating matrix, and evidence-driven deterministic risk triggers |
| `wave_guidance.json` | Heuristics for pilot wave sizing, network affinity, and soak periods |

---

## Controlled Reference Update Process (E15B.2)

Landfall **never** downloads arbitrary unverified updates from GitHub during runtime or assessment execution.
Updates follow a strictly controlled process:

1. **Upstream Review**: Review upstream release or commit in `github.com/Azure/migration`.
2. **Licensing & Integrity Check**: Confirm MIT license and calculate artifact SHA-256 hash.
3. **Parse & Normalize**: Run update script to map upstream sheets/checklists to `references/meg/*.json`.
4. **Regression Testing**: Execute `pytest tests/test_meg_readiness.py` to confirm schema backward compatibility.
5. **Commit & Version**: Commit updated JSON files and increment `parser_version` in `metadata.json`.
