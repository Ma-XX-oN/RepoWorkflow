# RepoWorkflow #583 — Current independent acceptance crosswalk

Snapshot: October 14, 2026 (Toronto).  74 cases: **50 PASS**,
**23 PARTIAL**, **1 FAIL**.  Last fully hosted-green integrated source:
`ac7618525674449b3326cd2881d4f100a368192b` in draft PR #666;
regression `38667171244`, integration `38667178515`.
This supplement retains the original 74-row historical acceptance ledger.

## Provider evidence key

- **A** — exact source `df6ebd91b73c6a6775b7f65ca42904cd84442320`
  regression `38662964029`; integration `38662973258`; PASS.
- **B** — exact source `4c902f4306a67a75364531dfe1b460b03f18e9de`
  regression `38664679611`; integration `38664686579`; PASS.
- **C** — exact source `f3aca87727d192d5908bbe98b7f77af988bd44bd`
  regression `38664901823`; integration `38664908686`; PASS.
- **D** — exact source `8385fc7daafbb4bcc2e9e5f14609053cf1a6c742`
  regression `38665477057`; integration `38665484649`; PASS.
- **E** — exact source `c37f9bab2a18ccc281c4b04ed8970b636202ebac`
  regression `38665903456`; integration `38665926447`; PASS.
- **F** — exact source `ac7618525674449b3326cd2881d4f100a368192b`
  regression `38667171244`; integration `38667178515`; PASS.

## Independent 74-case verdicts

- **T01 — PARTIAL**
  Historical anchor: test_all_state_action_pairs_from_independent_contract
  Remaining: 42 persistent state/action requests PASS, including 34 rejected;
  authorisation/review evidence for positive transitions not independently
  proven
- **T02 — PARTIAL**
  Historical anchor: test_all_state_action_pairs_from_independent_contract
  Remaining: 42 persistent state/action requests PASS, including 34 rejected;
  authorisation/review evidence for positive transitions not independently
  proven
- **T03 — PARTIAL**
  Historical anchor: test_all_state_action_pairs_from_independent_contract
  Remaining: 42 persistent state/action requests PASS, including 34 rejected;
  authorisation/review evidence for positive transitions not independently
  proven
- **T04 — PARTIAL**
  Historical anchor: test_all_state_action_pairs_from_independent_contract
  Remaining: 42 persistent state/action requests PASS, including 34 rejected;
  authorisation/review evidence for positive transitions not independently
  proven
- **T05 — PARTIAL**
  Historical anchor: test_all_state_action_pairs_from_independent_contract
  Remaining: 42 persistent state/action requests PASS, including 34 rejected;
  authorisation/review evidence for positive transitions not independently
  proven
- **T06 — PARTIAL**
  Historical anchor: test_all_state_action_pairs_from_independent_contract
  Remaining: 42 persistent state/action requests PASS, including 34 rejected;
  authorisation/review evidence for positive transitions not independently
  proven
- **T07 — PARTIAL**
  Historical anchor: test_all_state_action_pairs_from_independent_contract
  Remaining: 42 persistent state/action requests PASS, including 34 rejected;
  authorisation/review evidence for positive transitions not independently
  proven
- **T08 — PARTIAL**
  Historical anchor: test_all_state_action_pairs_from_independent_contract
  Remaining: 42 persistent state/action requests PASS, including 34 rejected;
  authorisation/review evidence for positive transitions not independently
  proven
- **L01 — PASS**
  Historical anchor:
  test_never_started_issue_projects_not_started_without_record
  Remaining: absent record produces not_started, no file
- **L02 — PASS**
  Historical anchor: test_missing_previously_committed_record_fails_closed
  Remaining: committed then missing fails closed
- **L03 — PASS** (provider evidence A)
  Verified full criterion via additional black-box oracle. Historical anchor:
  test_schema_one_reads_with_empty_high_risk_aliases
- **L04 — PASS** (provider evidence A)
  Verified full criterion via additional black-box oracle. Historical anchor:
  test_legacy_active_accept_remains_valid_after_upgrade
- **L05 — PASS** (provider evidence A)
  Verified full criterion via additional black-box oracle. Historical anchor:
  test_high_risk_aliases_round_trip_with_lifecycle
- **L06 — PASS** (provider evidence A)
  Verified full criterion via additional black-box oracle. Historical anchor:
  test_legacy_active_accept_remains_valid_after_upgrade
- **L07 — PARTIAL**
  Historical anchor:
  test_legal_lifecycle_round_trip_preserves_append_only_history
  Remaining: round trip PASS, but repeated migrations/revisions not
  exhaustively tested
- **L08 — PARTIAL**
  Historical anchor: test_all_state_action_pairs_from_independent_contract
  Remaining: four-step path and persistence exercised in setup; required
  review/validation evidence not certified
- **L09 — PARTIAL**
  Historical anchor:
  test_review_rejection_and_reentry_do_not_satisfy_dependency
  Remaining: rejection PASS; resubmit with changed evidence retention not fully
  verified
- **L10 — PARTIAL**
  Historical anchor:
  test_review_candidate_cannot_change_at_acceptance_or_completion
  Remaining: candidate mismatch refused; explicit active restart/revalidation
  absent
- **L11 — PASS** (provider evidence D)
  Verified full criterion via additional black-box oracle. Historical anchor:
  test_legal_lifecycle_round_trip_preserves_append_only_history
- **L12 — PASS**
  Historical anchor: test_illegal_transition_fails_without_mutation
  Remaining: rejected transition preserves full readback
- **L13 — PASS** (provider evidence A)
  Verified full criterion via additional black-box oracle. Historical anchor:
  test_default_graph_reads_saved_status_and_ignores_provider_closed
- **L14 — PASS**
  Historical anchor: test_all_state_action_pairs_from_independent_contract
  Remaining: dependency satisfaction checked after every legal state transition
- **L15 — PARTIAL**
  Historical anchor: test_missing_previously_committed_record_fails_closed
  Remaining: committed history recognized; lost clone/session ownership not
  independently validated
- **L16 — PASS** (provider evidence D)
  Verified full criterion via additional black-box oracle. Historical anchor:
  test_malformed_value_fails_closed
- **L17 — PARTIAL**
  Historical anchor:
  test_review_candidate_cannot_change_at_acceptance_or_completion
  Remaining: submit missing / accept mismatch / complete mismatch, not
  exhaustive forged/changed evidence
- **L18 — PARTIAL**
  Historical anchor: test_stale_or_unauthenticated_validation_denied;
  test_stale_authorization_denied
  Remaining: Pure #108 planner rejects stale/missing evidence; actual
  after-acceptance executor readback pending.
- **L19 — PASS** (provider evidence D)
  Verified full criterion via additional black-box oracle. Historical anchor:
  test_durable_reference_validation_detects_lifecycle_staleness
- **L20 — PARTIAL**
  Historical anchor: test_unverified_mit_applicability_denies_integration;
  test_readiness_has_explicit_parent_and_release
  Remaining: Pure planner verifies MIT applicability with no invented MIT;
  actual #109 ART/AIT execution pending.
- **C01 — PASS**
  Historical anchor:
  test_start_creates_revision_zero_and_normalized_active_state
  Remaining: lifecycle create revision 0 with issue identity
- **C02 — PASS**
  Historical anchor: test_create_and_replace_preserve_revision_provenance
  Remaining: CAS replacement, N+1 revision and exact readback
- **C03 — PASS**
  Historical anchor: test_stale_revision_fails_without_mutation
  Remaining: lifecycle stale revision refusal/readback
- **C04 — PASS** (provider evidence D)
  Verified full criterion via additional black-box oracle. Historical anchor:
  test_two_processes_racing_same_revision_have_one_winner
- **C05 — PASS** (provider evidence A)
  Verified full criterion via additional black-box oracle. Historical anchor:
  test_independent_keys_advance_independently
- **C06 — PASS**
  Historical anchor: test_failed_atomic_replace_preserves_prior_record
  Remaining: injected publish failure preserves old authoritative record
- **C07 — PARTIAL**
  Historical anchor:
  test_interrupted_committed_materialization_is_replayed_idempotently
  Remaining: Transaction replay tested locally, but lost remote publication
  ACK/exact request identity not proven.
- **C08 — PASS** (provider evidence C)
  Verified full criterion via additional black-box oracle. Historical anchor:
  test_recovery_never_assumes_prepared_is_committed;
  test_recovery_aborts_stale_prepared_transaction
- **C09 — PASS** (provider evidence C)
  Verified full criterion via additional black-box oracle. Historical anchor:
  test_interrupted_committed_materialization_is_replayed_idempotently
- **C10 — PARTIAL**
  Historical anchor: test_recovery_aborts_stale_prepared_transaction;
  test_committed_transaction_cannot_abort
  Remaining: Abort state and refusal tested; staging cleanup for real
  multi-record failure pending.
- **C11 — PASS** (provider evidence E)
  Verified full criterion via additional black-box oracle. Historical anchor:
  test_conflicting_prepared_transaction_blocks_new_prepare
- **C12 — PARTIAL**
  Historical anchor:
  test_conflicting_lifecycle_revisions_reject_stale_remote_push
  Remaining: Two local independent clones and shared bare remote reject stale
  push; authenticated provider path not proven.
- **C13 — PASS**
  Historical anchor: test_malformed_identity_and_payload_fail_closed
  Remaining: invalid writer/session identity rejects mutation
- **P01 — PASS**
  Historical anchor: test_csv_is_canonical_and_restart_readable
  Remaining: legacy three-column CSV persists and reads; unknown glyph
  separately checked
- **P02 — PASS** (provider evidence A)
  Verified full criterion via additional black-box oracle. Historical anchor:
  test_explicit_state_refresh_upgrades_csv_and_preserves_snapshot
- **P03 — PASS**
  Historical anchor:
  test_explicit_state_refresh_upgrades_csv_and_preserves_snapshot
  Remaining: proven absent records projected not_started with null revision
- **P04 — PASS**
  Historical anchor:
  test_explicit_state_refresh_upgrades_csv_and_preserves_snapshot
  Remaining: existing active record projected with revision 0
- **P05 — PASS**
  Historical anchor: test_malformed_cached_state_is_rejected
  Remaining: malformed/unknown status rejected
- **P06 — PASS** (provider evidence C)
  Verified full criterion via additional black-box oracle. Historical anchor:
  test_explicit_state_refresh_upgrades_csv_and_preserves_snapshot
- **P07 — PASS**
  Historical anchor:
  test_explicit_state_refresh_upgrades_csv_and_preserves_snapshot
  Remaining: authoritative change leaves old cached state until explicit
  refresh
- **P08 — PASS**
  Historical anchor: test_refresh_failure_does_not_mutate_csv
  Remaining: failed refresh leaves old CSV byte-identical
- **P09 — PASS** (provider evidence A)
  Verified full criterion via additional black-box oracle. Historical anchor:
  test_stale_refresh_revision_preserves_prior_csv
- **P10 — PASS** (provider evidence A)
  Verified full criterion via additional black-box oracle. Historical anchor:
  test_replace_uses_content_cas_and_preserves_prior_on_stale_write
- **P11 — PASS** (provider evidence A)
  Verified full criterion via additional black-box oracle. Historical anchor:
  test_failed_atomic_replace_preserves_prior_record
- **P12 — PARTIAL**
  Historical anchor: test_divergent_title_uses_provider_authority
  Remaining: provider title conflict resolved, lifecycle unchanged not
  independently asserted
- **P13 — PASS**
  Historical anchor:
  test_default_graph_reads_saved_status_and_ignores_provider_closed
  Remaining: provider closed does not override active cached lifecycle
- **P14 — PASS**
  Historical anchor: test_non_overlapping_changes_merge_without_provider
  Remaining: one-sided dependency/title changes merge
- **P15 — PASS**
  Historical anchor: test_divergent_status_snapshots_conflict
  Remaining: divergent state/revision conflict instead of last-writer-wins
- **P16 — PASS** (provider evidence F)
  Verified full criterion via additional black-box oracle. Historical anchor:
  test_malformed_cached_state_is_rejected
- **P17 — PASS**
  Historical anchor:
  test_conflicting_lifecycle_revisions_reject_stale_remote_push
  Remaining: Fresh independent Git clone reads same authoritative lifecycle
  candidate, revision and byte-identical cached five-column CSV; stale second
  clone cannot publish competing lifecycle/CSV. This is a local bare-remote
  transport test, not authenticated GitHub provider proof.
- **P18 — PASS** (provider evidence B)
  Verified full criterion via additional black-box oracle. Historical anchor:
  test_invalid_cycle_fails_before_write
- **G01 — FAIL**
  Historical anchor: test_graph_uses_cached_states_until_explicit_refresh
  Hosted RED .0.18 runs 38667588818 and 38667595895: default public select
  requires provider configuration on a fully cached graph. Narrow .0.20
  remediation pending full gates.
- **G02 — PASS**
  Historical anchor: test_graph_uses_cached_states_until_explicit_refresh
  Remaining: unknown state glyph before migration rather than completed
- **G03 — PASS**
  Historical anchor: test_all_six_lifecycle_glyphs_render_from_csv
  Remaining: all six glyphs rendered from status
- **G04 — PASS** (provider evidence D)
  Verified full criterion via additional black-box oracle. Historical anchor:
  test_projection_distinguishes_dependencies_and_lifecycle_states
- **G05 — PARTIAL**
  Historical anchor: test_graph_uses_cached_states_until_explicit_refresh
  Remaining: six-node --current refresh/save/render PASS; zero/one display
  cardinalities missing
- **G06 — PASS** (provider evidence F)
  Verified full criterion via additional black-box oracle. Historical anchor:
  test_default_graph_reads_saved_status_and_ignores_provider_closed
- **G07 — PASS**
  Historical anchor:
  test_current_cli_failure_has_no_graph_output_or_partial_csv
  Remaining: Public --current CLI raises visible error, does not emit partial
  graph or mutate CSV.
- **G08 — PASS**
  Historical anchor: test_graph_replacement_preserves_cached_status
  Remaining: title/topology replacement retains cached state
- **G09 — PASS**
  Historical anchor: test_opt_in_legend_is_after_graph_and_read_only
  Remaining: legend opt-in and read-only output
- **G10 — PASS**
  Historical anchor: test_legend_rejects_json_and_count_without_mutation
  Remaining: Both incompatible non-graph modes rejected with no output/CSV or
  lane state mutation.
- **G11 — PASS**
  Historical anchor:
  test_legend_current_debug_and_lane_filter_preserve_lifecycle
  Remaining: Actual CLI --current/--legend/--debug/lane-filter composition
  verifies graph and stable lifecycle.
- **G12 — PARTIAL**
  Historical anchor: test_formatter_controls_encoded_text_and_display_width
  Remaining: render width cases pass; complete layout/cartesian input matrix
  unproven
- **G13 — PARTIAL**
  Historical anchor: test_symbols_use_one_terminal_cell
  Remaining: terminal-width assertion and hosted OS probes pass, accessibility
  under all terminals not observed
- **G14 — PASS** (provider evidence D)
  Verified full criterion via additional black-box oracle. Historical anchor:
  test_projection_distinguishes_dependencies_and_lifecycle_states
- **G15 — PASS**
  Historical anchor:
  test_repeated_current_refresh_has_identical_csv_and_lifecycle
  Remaining: Two unchanged refreshes have byte-identical CSV, equal revision,
  unchanged lifecycle.

## In-flight verification (not yet accepted)

- **.0.20** — `dec94d58920d39e530a51a17f3bebe65d1f0b0a4`
  G01 lazy provider configuration. Regression invocation
  5d22fbfc942af54aae6aad7c21062289be3d9335; integration invocation
  d36f576326d0b570dbf548b2621ddef074a31411. No terminal verdict claimed.
- **.0.21** — `1f6c777dd154b80c8dc2f56e4494dccf2f9491ac`
  G01 repair plus G12 graph determinism. Regression invocation
  bdf5a0f271415f0e5ebc50d1b4973eb4c5144757; integration invocation
  ad441bd348851706dc42f3125a7ca8674a76d0b0. No terminal verdict claimed.
- **.0.22** — `273fd951e519318bef93026b99b16eac6e3e3f99`
  L15 lost independent clone and writer session. Regression invocation
  5de95dea09c3d0f15bb1e05499ef1a2c440ef114; integration invocation
  161d24978a9e886b2d3704353de8cbe9cfb11302. No terminal verdict claimed.
- **.0.23** — `129ace4598b7d8134dad629978446121bc64ff7e`
  G12 six-state topology/ordering matrix. Regression invocation
  fda492a99b2b9f0dadddb925bef4188c3585758d; integration invocation
  8d2ca634a14a855b4e3d85f0d8a19c655b9882cf. No terminal verdict claimed.

## Boundary rules

Real mutating-executor review and authorization gates belong to #109; do not
accept read-only planner #108 as proof. C12 requires live Git-hosted two-actor
lifecycle execution and fresh-clone readback, separate from local bare-remote
and authenticated reference-CAS tests. Mocked provider title authority is not
live provider proof. Generic green regression does not accept missing or failed
oracles. No main merge, stable release, protected #85 activation or #583
closure without all gates and explicit authorization.
