# Issue #629 — independent convergence certification matrix

This is a specification-derived preparatory test plan for #543, not a claim
that the assembled workflow is certified. Every provider-only observation
remains PENDING until a real provider result and exact candidate are recorded.

| ID | Requirement | Independent executable check | Live status |
| --- | --- | --- | --- |
| M01 | Six public test command families | test_contract_command_families | PENDING CLI integration |
| M02 | No, one, many, invalid selections | test_selection_partition | PENDING CLI integration |
| M03 | Local/hosted evidence identity equivalence | test_evidence_equivalence | PENDING provider |
| M04 | Failed, missing, stale, replayed evidence rejected | test_evidence_rejection | PENDING provider |
| M05 | Exact source/test/catalogue SHA binding | test_sha_binding | PENDING provider |
| M06 | Dedicated invocation marker; ordinary pushes free | test_marker_contract | PENDING hosted workflow |
| M07 | Linux, Windows, macOS required matrix | test_platform_coverage | PENDING hosted matrix |
| M08 | Protected main refuses direct push and bypass | test_protected_main_refusal | PENDING repository settings |
| M09 | Changed destination invalidates acceptance | test_destination_freshness | PENDING #542 |
| M10 | Repeat identical accepted PASS skips execution | test_reuse_and_invalidation | PENDING assembled provider |
| M11 | Incomplete, failed and unavailable provider results | test_provider_failure_states | PENDING provider |
| M12 | Authenticated hosted artifact identity | test_provider_attestation | PENDING provider |

Fixture authority:
- #538: CI_INVOCATION_CONTRACT.md and PUBLIC_WORKFLOW.md §10.1.
- #540: exact committed .ci/run parser and dedicated invocation ancestry.
- #548: provider-attested canonical testResults-<issue>.jsonl and cache identity.
- Current public CLI grammar: PUBLIC_WORKFLOW.md and current #545 contract.

Tests must use real Git history for ancestry, not fabricated SHA relationships.
Provider evidence is never marked PASS by synthetic fixtures. In particular,
successful subprocess return codes do not certify GitHub branch protection,
hosted result authenticity, cost, or runner coverage.

The machine-readable matrix lives in tests/fixtures/issue629_matrix.json.
Its 'pending' entries are deliberate, not skipped success.
