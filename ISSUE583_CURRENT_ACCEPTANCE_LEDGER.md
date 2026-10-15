# RepoWorkflow #583 — Current Independent Acceptance Crosswalk

**Snapshot**: October 14, 2026 (Toronto); 74 cases: **50 PASS / 23 PARTIAL / 1 FAIL**. This document supplements, but does not overwrite, the historical `ISSUE583_INDEPENDENT_ACCEPTANCE_LEDGER.md`. Exact source last fully hosted GREEN: `ac7618525674449b3326cd2881d4f100a368192b` (PR #666), regression run `38667171244` and integration run `38667178515`. This source includes all verified promotions below except C11 (separately certified .0.15 and reassembled unchanged in .0.17). Nothing here constitutes final #583 approval.

## Per-case evidence and disposition

| ID | Status | Independent evidence | Outstanding boundary |
|---|---|---|---|
| T01 | PARTIAL | Historical: test_all_state_action_pairs_from_independent_contract | 42 persistent state/action requests PASS, including 34 rejected; authorisation/review evidence for positive transitions not independently proven |
| T02 | PARTIAL | Historical: test_all_state_action_pairs_from_independent_contract | 42 persistent state/action requests PASS, including 34 rejected; authorisation/review evidence for positive transitions not independently proven |
| T03 | PARTIAL | Historical: test_all_state_action_pairs_from_independent_contract | 42 persistent state/action requests PASS, including 34 rejected; authorisation/review evidence for positive transitions not independently proven |
| T04 | PARTIAL | Historical: test_all_state_action_pairs_from_independent_contract | 42 persistent state/action requests PASS, including 34 rejected; authorisation/review evidence for positive transitions not independently proven |
| T05 | PARTIAL | Historical: test_all_state_action_pairs_from_independent_contract | 42 persistent state/action requests PASS, including 34 rejected; authorisation/review evidence for positive transitions not independently proven |
| T06 | PARTIAL | Historical: test_all_state_action_pairs_from_independent_contract | 42 persistent state/action requests PASS, including 34 rejected; authorisation/review evidence for positive transitions not independently proven |
| T07 | PARTIAL | Historical: test_all_state_action_pairs_from_independent_contract | 42 persistent state/action requests PASS, including 34 rejected; authorisation/review evidence for positive transitions not independently proven |
| T08 | PARTIAL | Historical: test_all_state_action_pairs_from_independent_contract | 42 persistent state/action requests PASS, including 34 rejected; authorisation/review evidence for positive transitions not independently proven |
| L01 | PASS | Historical: test_never_started_issue_projects_not_started_without_record | Fully exercised by listed exact-source acceptance for this case |
| L02 | PASS | Historical: test_missing_previously_committed_record_fails_closed | Fully exercised by listed exact-source acceptance for this case |
| L03 | PASS | Hosted 38662964029 / 38662973258; source `df6ebd91b73c` | Fully exercised by listed exact-source acceptance for this case |
| L04 | PASS | Hosted 38662964029 / 38662973258; source `df6ebd91b73c` | Fully exercised by listed exact-source acceptance for this case |
| L05 | PASS | Hosted 38662964029 / 38662973258; source `df6ebd91b73c` | Fully exercised by listed exact-source acceptance for this case |
| L06 | PASS | Hosted 38662964029 / 38662973258; source `df6ebd91b73c` | Fully exercised by listed exact-source acceptance for this case |
| L07 | PARTIAL | Historical: test_legal_lifecycle_round_trip_preserves_append_only_history | round trip PASS, but repeated migrations/revisions not exhaustively tested |
| L08 | PARTIAL | Historical: test_all_state_action_pairs_from_independent_contract | four-step path and persistence exercised in setup; required review/validation evidence not certified |
| L09 | PARTIAL | Historical: test_review_rejection_and_reentry_do_not_satisfy_dependency | rejection PASS; resubmit with changed evidence retention not fully verified |
| L10 | PARTIAL | Historical: test_review_candidate_cannot_change_at_acceptance_or_completion | candidate mismatch refused; explicit active restart/revalidation absent |
| L11 | PASS | Hosted 38665477057 / 38665484649; source `8385fc7daafb` | Fully exercised by listed exact-source acceptance for this case |
| L12 | PASS | Historical: test_illegal_transition_fails_without_mutation | Fully exercised by listed exact-source acceptance for this case |
| L13 | PASS | Hosted 38662964029 / 38662973258; source `df6ebd91b73c` | Fully exercised by listed exact-source acceptance for this case |
| L14 | PASS | Historical: test_all_state_action_pairs_from_independent_contract | Fully exercised by listed exact-source acceptance for this case |
| L15 | PARTIAL | Historical: test_missing_previously_committed_record_fails_closed | committed history recognized; lost clone/session ownership not independently validated |
| L16 | PASS | Hosted 38665477057 / 38665484649; source `8385fc7daafb` | Fully exercised by listed exact-source acceptance for this case |
| L17 | PARTIAL | Historical: test_review_candidate_cannot_change_at_acceptance_or_completion | submit missing / accept mismatch / complete mismatch, not exhaustive forged/changed evidence |
| L18 | PARTIAL | Historical: test_stale_or_unauthenticated_validation_denied; test_stale_authorization_denied | Pure #108 planner rejects stale/missing evidence; actual after-acceptance executor readback pending. |
| L19 | PASS | Hosted 38665477057 / 38665484649; source `8385fc7daafb` | Fully exercised by listed exact-source acceptance for this case |
| L20 | PARTIAL | Historical: test_unverified_mit_applicability_denies_integration; test_readiness_has_explicit_parent_and_release | Pure planner verifies MIT applicability with no invented MIT; actual #109 ART/AIT execution pending. |
| C01 | PASS | Historical: test_start_creates_revision_zero_and_normalized_active_state | Fully exercised by listed exact-source acceptance for this case |
| C02 | PASS | Historical: test_create_and_replace_preserve_revision_provenance | Fully exercised by listed exact-source acceptance for this case |
| C03 | PASS | Historical: test_stale_revision_fails_without_mutation | Fully exercised by listed exact-source acceptance for this case |
| C04 | PASS | Hosted 38665477057 / 38665484649; source `8385fc7daafb` | Fully exercised by listed exact-source acceptance for this case |
| C05 | PASS | Hosted 38662964029 / 38662973258; source `df6ebd91b73c` | Fully exercised by listed exact-source acceptance for this case |
| C06 | PASS | Historical: test_failed_atomic_replace_preserves_prior_record | Fully exercised by listed exact-source acceptance for this case |
| C07 | PARTIAL | Historical: test_interrupted_committed_materialization_is_replayed_idempotently | Transaction replay tested locally, but lost remote publication ACK/exact request identity not proven. |
| C08 | PASS | Hosted 38664901823 / 38664908686; source `f3aca87727d1` | Fully exercised by listed exact-source acceptance for this case |
| C09 | PASS | Hosted 38664901823 / 38664908686; source `f3aca87727d1` | Fully exercised by listed exact-source acceptance for this case |
| C10 | PARTIAL | Historical: test_recovery_aborts_stale_prepared_transaction; test_committed_transaction_cannot_abort | Abort state and refusal tested; staging cleanup for real multi-record failure pending. |
| C11 | PASS | Hosted 38665903456 / 38665926447; source `c37f9bab2a18` | Fully exercised by listed exact-source acceptance for this case |
| C12 | PARTIAL | Historical: test_conflicting_lifecycle_revisions_reject_stale_remote_push | Two local independent clones and shared bare remote reject stale push; authenticated provider path not proven. |
| C13 | PASS | Historical: test_malformed_identity_and_payload_fail_closed | Fully exercised by listed exact-source acceptance for this case |
| P01 | PASS | Historical: test_csv_is_canonical_and_restart_readable | Fully exercised by listed exact-source acceptance for this case |
| P02 | PASS | Hosted 38662964029 / 38662973258; source `df6ebd91b73c` | Fully exercised by listed exact-source acceptance for this case |
| P03 | PASS | Historical: test_explicit_state_refresh_upgrades_csv_and_preserves_snapshot | Fully exercised by listed exact-source acceptance for this case |
| P04 | PASS | Historical: test_explicit_state_refresh_upgrades_csv_and_preserves_snapshot | Fully exercised by listed exact-source acceptance for this case |
| P05 | PASS | Historical: test_malformed_cached_state_is_rejected | Fully exercised by listed exact-source acceptance for this case |
| P06 | PASS | Hosted 38664901823 / 38664908686; source `f3aca87727d1` | Fully exercised by listed exact-source acceptance for this case |
| P07 | PASS | Historical: test_explicit_state_refresh_upgrades_csv_and_preserves_snapshot | Fully exercised by listed exact-source acceptance for this case |
| P08 | PASS | Historical: test_refresh_failure_does_not_mutate_csv | Fully exercised by listed exact-source acceptance for this case |
| P09 | PASS | Hosted 38662964029 / 38662973258; source `df6ebd91b73c` | Fully exercised by listed exact-source acceptance for this case |
| P10 | PASS | Hosted 38662964029 / 38662973258; source `df6ebd91b73c` | Fully exercised by listed exact-source acceptance for this case |
| P11 | PASS | Hosted 38662964029 / 38662973258; source `df6ebd91b73c` | Fully exercised by listed exact-source acceptance for this case |
| P12 | PARTIAL | Historical: test_divergent_title_uses_provider_authority | provider title conflict resolved, lifecycle unchanged not independently asserted |
| P13 | PASS | Historical: test_default_graph_reads_saved_status_and_ignores_provider_closed | Fully exercised by listed exact-source acceptance for this case |
| P14 | PASS | Historical: test_non_overlapping_changes_merge_without_provider | Fully exercised by listed exact-source acceptance for this case |
| P15 | PASS | Historical: test_divergent_status_snapshots_conflict | Fully exercised by listed exact-source acceptance for this case |
| P16 | PASS | Hosted 38667171244 / 38667178515; source `ac7618525674` | Fully exercised by listed exact-source acceptance for this case |
| P17 | PASS | Historical: test_conflicting_lifecycle_revisions_reject_stale_remote_push | Fully exercised by listed exact-source acceptance for this case |
| P18 | PASS | Hosted 38664679611 / 38664686579; source `4c902f4306a6` | Fully exercised by listed exact-source acceptance for this case |
| G01 | FAIL | Historical: test_graph_uses_cached_states_until_explicit_refresh | Hosted RED `.0.18` (38667588818/38667595895), provider config required for cached public select; `.0.20` staged repair unverified |
| G02 | PASS | Historical: test_graph_uses_cached_states_until_explicit_refresh | Fully exercised by listed exact-source acceptance for this case |
| G03 | PASS | Historical: test_all_six_lifecycle_glyphs_render_from_csv | Fully exercised by listed exact-source acceptance for this case |
| G04 | PASS | Hosted 38665477057 / 38665484649; source `8385fc7daafb` | Fully exercised by listed exact-source acceptance for this case |
| G05 | PARTIAL | Historical: test_graph_uses_cached_states_until_explicit_refresh | six-node --current refresh/save/render PASS; zero/one display cardinalities missing |
| G06 | PASS | Hosted 38667171244 / 38667178515; source `ac7618525674` | Fully exercised by listed exact-source acceptance for this case |
| G07 | PASS | Historical: test_current_cli_failure_has_no_graph_output_or_partial_csv | Fully exercised by listed exact-source acceptance for this case |
| G08 | PASS | Historical: test_graph_replacement_preserves_cached_status | Fully exercised by listed exact-source acceptance for this case |
| G09 | PASS | Historical: test_opt_in_legend_is_after_graph_and_read_only | Fully exercised by listed exact-source acceptance for this case |
| G10 | PASS | Historical: test_legend_rejects_json_and_count_without_mutation | Fully exercised by listed exact-source acceptance for this case |
| G11 | PASS | Historical: test_legend_current_debug_and_lane_filter_preserve_lifecycle | Fully exercised by listed exact-source acceptance for this case |
| G12 | PARTIAL | Historical: test_formatter_controls_encoded_text_and_display_width | render width cases pass; complete layout/cartesian input matrix unproven |
| G13 | PARTIAL | Historical: test_symbols_use_one_terminal_cell | terminal-width assertion and hosted OS probes pass, accessibility under all terminals not observed |
| G14 | PASS | Hosted 38665477057 / 38665484649; source `8385fc7daafb` | Fully exercised by listed exact-source acceptance for this case |
| G15 | PASS | Historical: test_repeated_current_refresh_has_identical_csv_and_lifecycle | Fully exercised by listed exact-source acceptance for this case |

## In-flight independent verification (not yet accepted)

- `.0.20` `dec94d58920d39e530a51a17f3bebe65d1f0b0a4`: G01 lazy provider configuration resolution; regression/integration commands `5d22fbfc942af54aae6aad7c21062289be3d9335` / `d36f576326d0b570dbf548b2621ddef074a31411`.
- `.0.21` `1f6c777dd154b80c8dc2f56e4494dccf2f9491ac`: G01 corrected source + graph-layout determinism; regression/integration commands `bdf5a0f271415f0e5ebc50d1b4973eb4c5144757` / `ad441bd348851706dc42f3125a7ca8674a76d0b0`.
- `.0.22` `273fd951e519318bef93026b99b16eac6e3e3f99`: L15 lost clone/session lifecycle continuation; commands `5de95dea09c3d0f15bb1e05499ef1a2c440ef114` / `161d24978a9e886b2d3704353de8cbe9cfb11302`.
- `.0.23` `129ace4598b7d8134dad629978446121bc64ff7e`: G12 six-state graph topology × ordering matrix; commands `fda492a99b2b9f0dadddb925bef4188c3585758d` / `8d2ca634a14a855b4e3d85f0d8a19c655b9882cf`.

## Non-substitution rules

Actual #109 mutating executor evidence and approval gates (T03, T08, L18, L20 and related transition authorisation) cannot be inferred from the #108 planner. Actual external shared-provider mutation conflicts are distinct from local Git bare-remote tests, and C12 remains partial. A generic regression PASS never upgrades unproven cases. Source-only inspection and mocked provider fixtures are not live provider certification. Preserve the failed G01 RED run. Protected main merges, stable release publication, and security #85 activation require separate authorization.
