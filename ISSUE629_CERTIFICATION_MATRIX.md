# Issue #629 — independent convergence certification

## Scope and completion boundary

This is preparatory verification for assembled certification issue #543.
An issue-629 test passing proves only that the named preliminary contract
check executed on that candidate.  It never establishes #543 acceptance.
Unfinished #541 and #85 provider/protection tests are explicitly PENDING.

## Authoritative handoffs

- #538: documentation commit `b279eee99a8c105df82aa93ea2122a33fe49edf4`
  (draft PR #539); `CI_INVOCATION_CONTRACT.md` defines the five stages,
  dedicated `.ci/run` commit and non-dispatching routine push semantics.
- #540: parser commit `e63ed04daac5014a500077076cbd324d489b0e4f`
  (draft PR #544); `repo_workflow/ci_invocation.py` is the executable
  contract, with real Git history, retry and malformed-marker tests.
- #548: evidence commit `0c52bdfe24ea8128f71aa41fb88c9037fa7abc1c`
  (draft PR #615, based on #613); canonical per-issue JSONL, provider
  attestation, applicable cache records and provider identity.
- #545 and #543: authoritative issue descriptions define the six-command
  CLI, RED/GREEN selection, local/hosted parity and final certification.

## Acceptance trace

Each record has an executable source path or an explicitly named
provider-only pending check.  `implemented` means the acceptance test
source exists; it does not imply the assembled candidate was executed.
Every row remains `PENDING` for final #543 certification.

- **M01 — Six public test families and spelling.**
  Prepared: `tests.test_issue629_cli_acceptance.UnifiedCliSpecificationTests.test_all_six_stage_help_paths`.
- **M02 — Single persisted RED selection; zero one many invalid.**
  Prepared: `tests.test_issue629_selection_acceptance.SelectionLifecycleAcceptanceTests.test_many_groups_still_selects_exactly_one`.
- **M03 — Stage help and --remote option grammar.**
  Prepared: `tests.test_issue629_cli_acceptance.UnifiedCliSpecificationTests.test_remote_option_is_documented_for_every_stage`.
- **M04 — Superseded validate commands absent.**
  Prepared: `tests.test_issue629_cli_acceptance.UnifiedCliSpecificationTests.test_legacy_validate_regression_and_integration_removed`.
- **M05 — Dedicated marker stage and pre-invocation tip.**
  Prepared: `tests.test_issue629_invocation_acceptance.InvocationContractAcceptanceTests.test_dedicated_commit_matches_parent`.
- **M06 — Missed invocation retry binds immediate previous tip.**
  Prepared: `tests.test_issue629_invocation_acceptance.InvocationContractAcceptanceTests.test_retry_binds_immediate_previous_tip`.
- **M07 — No paid testing on ordinary push.**
  Pending: `tests.test_issue629_pending_provider.PendingAssembledProviderAcceptance.test_no_ordinary_push_dispatch`.
  Reason: Assembled provider/security evidence belongs to #543 after prerequisites.
- **M08 — Remote results reading triggers no new run.**
  Pending: `tests.test_issue629_pending_provider.PendingAssembledProviderAcceptance.test_results_remote_is_read_only`.
  Reason: Assembled provider/security evidence belongs to #543 after prerequisites.
- **M09 — Local and hosted stages select equivalent tests.**
  Pending: `tests.test_issue629_pending_provider.PendingAssembledProviderAcceptance.test_local_hosted_selection_parity`.
  Reason: Assembled provider/security evidence belongs to #543 after prerequisites.
- **M10 — Canonical per-issue testing log write.**
  Prepared: `tests.test_issue629_stage_cardinality.LocalStageCardinalityTests.test_one_temporary_group_runs_and_records_exact_source`.
- **M11 — Local results reads canonical log.**
  Prepared: `tests.test_issue629_stage_cardinality.LocalStageCardinalityTests.test_one_real_local_record_returned_exactly`.
- **M12 — Remote results retrieves provider records.**
  Pending: `tests.test_issue629_pending_provider.PendingAssembledProviderAcceptance.test_remote_results_retrieval`.
  Reason: Assembled provider/security evidence belongs to #543 after prerequisites.
- **M13 — No one many invalid for each stage.**
  Prepared: `tests.test_issue629_stage_cardinality.LocalStageCardinalityTests`.
  Reason: Provider-dependent stage permutations still pending.
  Scope: Local RED, GREEN, temporary and results partitions; regression/integration live permutations remain PENDING #543.
- **M14 — Malformed or stale RED selection rejected.**
  Prepared: `tests.test_issue629_selection_acceptance.SelectionLifecycleAcceptanceTests.test_invalid_foreign_or_unregistered_group_refused`.
- **M15 — Missing selection warns and records SKIPPED not PASS.**
  Prepared: `tests.test_issue629_stage_cardinality.LocalStageCardinalityTests.test_missing_green_selection_records_skipped_not_pass`.
- **M16 — Temporary catalogue path and cleanup.**
  Prepared: `tests.test_issue629_stage_cardinality.LocalStageCardinalityTests.test_integration_refuses_unremoved_temporary_sandbox`.
- **M17 — Expected RED vs unexpected exit and infrastructure failures.**
  Prepared: `tests.test_issue629_red_outcome.RedOutcomeAcceptanceTests.test_expected_exit_and_stderr_or_stdout_signature_is_red`.
- **M18 — Unchanged accepted GREEN PASS actually bypasses subprocess.**
  Pending: `tests.test_issue629_pending_provider.PendingAssembledProviderAcceptance.test_reuse_without_subprocess`.
  Reason: Assembled provider/security evidence belongs to #543 after prerequisites.
- **M19 — Changed inputs invalidate applicable cached evidence.**
  Pending: `tests.test_issue629_pending_provider.PendingAssembledProviderAcceptance.test_changed_inputs_cache_invalidation`.
  Reason: Assembled provider/security evidence belongs to #543 after prerequisites.
- **M20 — Exact candidate and catalogue SHA binding.**
  Prepared: `tests.test_issue629_provider_probe.LiveProviderMetadataTests.test_completed_successful_run_exact_invocation_sha`.
- **M21 — Reject failed missing stale or replayed evidence.**
  Pending: `tests.test_issue629_pending_provider.PendingAssembledProviderAcceptance.test_evidence_failure_matrix`.
  Reason: Assembled provider/security evidence belongs to #543 after prerequisites.
- **M22 — Reject forged/malformed external evidence.**
  Pending: `tests.test_issue629_pending_provider.PendingAssembledProviderAcceptance.test_forged_provider_evidence`.
  Reason: Assembled provider/security evidence belongs to #543 after prerequisites.
- **M23 — Linux Windows and macOS hosted matrix.**
  Pending: `tests.test_issue629_pending_provider.PendingAssembledProviderAcceptance.test_required_platform_matrix`.
  Reason: Assembled provider/security evidence belongs to #543 after prerequisites.
- **M24 — Protected main refuses direct push bypass force delete.**
  Pending: `tests.test_issue629_pending_provider.PendingAssembledProviderAcceptance.test_protected_main_refusal`.
  Reason: Assembled provider/security evidence belongs to #543 after prerequisites.
- **M25 — Stale destination race rejects later candidate atomically.**
  Pending: `tests.test_issue629_pending_provider.PendingAssembledProviderAcceptance.test_destination_race`.
  Reason: Assembled provider/security evidence belongs to #543 after prerequisites.
- **M26 — Reconcile required checks and documentation.**
  Pending: `tests.test_issue629_pending_provider.PendingAssembledProviderAcceptance.test_protection_and_docs_contract`.
  Reason: Assembled provider/security evidence belongs to #543 after prerequisites.
- **M27 — Provider immutable artifact lookup.**
  Prepared: `tests.test_issue629_provider_probe.LiveProviderMetadataTests.test_provider_run_has_named_unexpired_artifact`.
- **M28 — Incomplete failed and unavailable provider outcomes.**
  Pending: `tests.test_issue629_pending_provider.PendingAssembledProviderAcceptance.test_provider_outcome_fail_closed`.
  Reason: Assembled provider/security evidence belongs to #543 after prerequisites.
- **M29 — Source-mixed request and uncommitted marker tamper.**
  Prepared: `tests.test_issue629_invocation_acceptance.InvocationContractAcceptanceTests.test_mixed_source_mutation_rejected`.

## Execution and false-GREEN rules

- The self-CI catalogue contains issue-629-specific groups that run
  Python `unittest` independently from the production code's tests.
- Subprocess tests launch the actual `./rwf` in disposable Git fixtures;
  real-Git marker tests require the assembled #540 implementation.
- Expected-RED tests cover strict declarations and RED, NOT_RED, FAIL,
  INCOMPLETE outcomes without inferring expectations from failures.
- Local cache tests require exact revision, catalogue, runner, platform,
  clean inputs, stable HEAD and latest applicable PASS.
- Live GitHub probes are read-only and opt-in; a missing live provider
  identity causes an explicit skip, never a synthetic PASS.
- Protected-main mutation refusal, paid ordinary-push absence, platform
  matrix, final provider parity and stale-parent races remain PENDING #543.
- PR #633 is draft; no branch merge or workflow activation is authorized.

## Constituent provider observation (not final certification)

#548 GREEN retry run `38066798486` had a successful validate job,
artifact `11674899611` (`provider-result-38066798486`, non-expired),
and a canonical JSONL group observation `reused=true` for candidate
`6019ac3afd01aaa0303a8fd01415d17ea2fbc3dc` after baseline run
`38066717494`.  This verifies a constituent handoff observation only.

## Final #543 obligations

After #541, #545, #542 and #85 are assembled, run all pending
scenarios against the identical exact candidate, actual GitHub provider
artifacts, protected server settings and supported OS targets.  Record
each candidate SHA, invocation, test catalogue revision, run/job/artifact
identity, platform, outcome and documented refusal.  Do not infer
certification from this preparatory PR's issue-scoped GREEN.
