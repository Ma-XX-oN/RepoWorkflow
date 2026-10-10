# Evidence-aware hosted/provider validation planner (#110)

## Authority and dependencies

This is the core planner for the #70 durable evidence importer and the #67
configured `repo-ci` provider. The validation requirements must be the complete
independently declared set of #95 atomic units, with #68 fingerprints based on
the effective source, catalogue, configuration, workflow and capabilities.

Use `repo_workflow.validation_plan.execute_from_store` for live planning and
execution. This function re-reads the #69 durable evidence store and calls
`import_from_store` before deciding which units can be reused.

The caller must independently establish:

- `trusted_record_ids`: authenticated durable provenance, not a filesystem
  listing or a claimed provider run identifier;
- `equivalent_candidate_shas`: source candidate identities proven equivalent
  over the complete per-unit effective input closure, not branch-name matches;
- the complete list of required automated and manual units, including MIT;
- provider stage-group mapping from the declared test catalogue.

Passing no trusted IDs or no equivalence proofs is safe. It results in more
automated work rather than false coverage. Missing proofs must never be
invented from successful subprocess return codes.

## Decision table

| Authenticated import result | Required mode | Action |
| --- | --- | --- |
| Applicable trusted PASS | Automated or manual | Reuse |
| Missing, stale, unusable | Automated | Execute |
| Missing, stale, unusable | Manual / MIT | Manual-required |

A completed provider subprocess yields an **observation**, not a new coverage
verdict. The core validation evidence/certification owner must publish and
classify the independently verified outcome. The planner never creates
manual evidence or a terminal PASS/FAIL/INCOMPLETE result.

## Execution boundary

`execute_from_store` produces the deterministic plan sorted by unit ID, then
sends only missing automated units to the existing versioned `repo-ci execute`
operation. A plan with no missing automated work never calls the provider.
The adapter must return one exact-candidate observation for every submitted
stage, with unique IDs and internally consistent completeness/outcome flags.
Any missing, extra, duplicate, mismatched or malformed observations fail
closed. Raw genuine FAIL and unavailable outcomes remain raw observations.

The provider selector remains `.ci/repo-ci.json`; #110 does not make
GitHub-specific runner policy or terminal classification authoritative.

## Verification

- `tests/test_validation_plan.py` tests import provenance, complete/reduced
  execution matrices, manual handling, malformed records, identity changes,
  duplicate/missing stage observations, unknown groups and failure handling.
- `tests/test_validation_plan_live.py` exercises a real configured provider
  subprocess and confirms only the missing stage executes while an
  independently created trusted PASS is reused.
- `.github/workflows/repo-ci-evidence-planner-acceptance.yml` runs all
  evidence and planner acceptance modules on Ubuntu, Windows and macOS.
- The full source regression runs in the separate GitHub certification job
  on the exact candidate SHA.

This is a successor-consumable execution interface. It does **not** grant
permission to merge #67/#70/#110, tag, release or change production policy.
