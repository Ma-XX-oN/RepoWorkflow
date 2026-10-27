# RepoWorkflow #583 — Independent Acceptance Ledger

> This ledger is an executed-evidence assessment, not the normative expected-result specification. See `SIX_STATE_ACCEPTANCE_MATRIX.md` for the 74 requirements.

**Scope:** existing #583 V3 claim `6134927670`, PR #658. **Status:** 27 full PASS, 47 PARTIAL, 0 full FAIL identified as of the previous exact certified source; not DONE. The 48 PARTIAL rows are not accepted. Latest certified source before P17 addition: `91caaee86c4d08c59c8a411d63a1c9f858dc0e13`, hosted regression run `38648373520`, integration run `38649138881`. Both executed 1,858 tests (14 historical provider-only skips), integration 9/9 platform jobs PASS. P17 local independent-clone reconstruction verified by hosted test at source `d3dd364f73df473b8c48f584c1bb92afa3817365` (provider run 38651029456), conditional on final provider GREEN evidence readback.

**Proof classes:** named test log + on-disk or provider readback; synthetic local fixtures are not live provider integration. A test anchor does not prove unexercised dimensions. `PARTIAL` retains an explicit unproven aspect. Some anchor names are in `tests/` and others in their `test_*.py` root modules.

| ID | Verdict | Independently run test anchor | Remaining limitation / observation |
| --- | --- | --- | --- |
| T01 | PARTIAL | test_all_state_action_pairs_from_independent_contract | 42 persistent state/action requests PASS, including 34 rejected; authorisation/review evidence for positive transitions not independently proven |
| T02 | PARTIAL | test_all_state_action_pairs_from_independent_contract | 42 persistent state/action requests PASS, including 34 rejected; authorisation/review evidence for positive transitions not independently proven |
| T03 | PARTIAL | test_all_state_action_pairs_from_independent_contract | 42 persistent state/action requests PASS, including 34 rejected; authorisation/review evidence for positive transitions not independently proven |
| T04 | PARTIAL | test_all_state_action_pairs_from_independent_contract | 42 persistent state/action requests PASS, including 34 rejected; authorisation/review evidence for positive transitions not independently proven |
| T05 | PARTIAL | test_all_state_action_pairs_from_independent_contract | 42 persistent state/action requests PASS, including 34 rejected; authorisation/review evidence for positive transitions not independently proven |
| T06 | PARTIAL | test_all_state_action_pairs_from_independent_contract | 42 persistent state/action requests PASS, including 34 rejected; authorisation/review evidence for positive transitions not independently proven |
| T07 | PARTIAL | test_all_state_action_pairs_from_independent_contract | 42 persistent state/action requests PASS, including 34 rejected; authorisation/review evidence for positive transitions not independently proven |
| T08 | PARTIAL | test_all_state_action_pairs_from_independent_contract | 42 persistent state/action requests PASS, including 34 rejected; authorisation/review evidence for positive transitions not independently proven |
| L01 | PASS | test_never_started_issue_projects_not_started_without_record | absent record produces not_started, no file |
| L02 | PASS | test_missing_previously_committed_record_fails_closed | committed then missing fails closed |
| L03 | PARTIAL | test_schema_one_reads_with_empty_high_risk_aliases | schema-1 normalized, but no exact first-write upgrade assertion |
| L04 | PARTIAL | test_legacy_active_accept_remains_valid_after_upgrade | legacy event count preserved; source does not explicitly compare every event field |
| L05 | PARTIAL | test_high_risk_aliases_round_trip_with_lifecycle | alias normalization and readback PASS; schema-2 migration shape not exercised here |
| L06 | PARTIAL | test_legacy_active_accept_remains_valid_after_upgrade | one legacy cardinality exercised; zero/one/many cross-product missing |
| L07 | PARTIAL | test_legal_lifecycle_round_trip_preserves_append_only_history | round trip PASS, but repeated migrations/revisions not exhaustively tested |
| L08 | PARTIAL | test_all_state_action_pairs_from_independent_contract | four-step path and persistence exercised in setup; required review/validation evidence not certified |
| L09 | PARTIAL | test_review_rejection_and_reentry_do_not_satisfy_dependency | rejection PASS; resubmit with changed evidence retention not fully verified |
| L10 | PARTIAL | test_review_candidate_cannot_change_at_acceptance_or_completion | candidate mismatch refused; explicit active restart/revalidation absent |
| L11 | PARTIAL | test_legal_lifecycle_round_trip_preserves_append_only_history | abort/re-entry exercised, not second abort generation proof |
| L12 | PASS | test_illegal_transition_fails_without_mutation | rejected transition preserves full readback |
| L13 | PARTIAL | test_default_graph_reads_saved_status_and_ignores_provider_closed | closed provider does not force completed, not all six × two provider statuses |
| L14 | PASS | test_all_state_action_pairs_from_independent_contract | dependency satisfaction checked after every legal state transition |
| L15 | PARTIAL | test_missing_previously_committed_record_fails_closed | committed history recognized; lost clone/session ownership not independently validated |
| L16 | PARTIAL | test_malformed_value_fails_closed | unsupported schema rejected; truncated/conflicting-history combinations not fully tested |
| L17 | PARTIAL | test_review_candidate_cannot_change_at_acceptance_or_completion | submit missing / accept mismatch / complete mismatch, not exhaustive forged/changed evidence |
| L18 | PARTIAL | test_stale_or_unauthenticated_validation_denied; test_stale_authorization_denied | Pure #108 planner rejects stale/missing evidence; actual after-acceptance executor readback pending. |
| L19 | PARTIAL | test_durable_reference_validation_detects_lifecycle_staleness | stale lifecycle reference checked; stale relationship revision consumption needs distinct proof |
| L20 | PARTIAL | test_unverified_mit_applicability_denies_integration; test_readiness_has_explicit_parent_and_release | Pure planner verifies MIT applicability with no invented MIT; actual #109 ART/AIT execution pending. |
| C01 | PASS | test_start_creates_revision_zero_and_normalized_active_state | lifecycle create revision 0 with issue identity |
| C02 | PASS | test_create_and_replace_preserve_revision_provenance | CAS replacement, N+1 revision and exact readback |
| C03 | PASS | test_stale_revision_fails_without_mutation | lifecycle stale revision refusal/readback |
| C04 | PARTIAL | test_two_processes_racing_same_revision_have_one_winner | two processes on generic record CAS; lifecycle-specific interleaving not tested |
| C05 | PARTIAL | test_independent_keys_advance_independently | independent keys don't interfere; truly concurrent independent issue writers not exercised |
| C06 | PASS | test_failed_atomic_replace_preserves_prior_record | injected publish failure preserves old authoritative record |
| C07 | PARTIAL | test_interrupted_committed_materialization_is_replayed_idempotently | Transaction replay tested locally, but lost remote publication ACK/exact request identity not proven. |
| C08 | PARTIAL | test_recovery_never_assumes_prepared_is_committed; test_recovery_aborts_stale_prepared_transaction | Prepared recovery state and revalidation tested; real multi-store crash/publish not proven. |
| C09 | PARTIAL | test_interrupted_committed_materialization_is_replayed_idempotently | Committed recovery replays same writes; real partially published multi-record reconstruction pending. |
| C10 | PARTIAL | test_recovery_aborts_stale_prepared_transaction; test_committed_transaction_cannot_abort | Abort state and refusal tested; staging cleanup for real multi-record failure pending. |
| C11 | PARTIAL | test_conflicting_prepared_transaction_blocks_new_prepare | Conflicting transaction rejected; durable provider clone interleaving pending. |
| C12 | PARTIAL | test_conflicting_lifecycle_revisions_reject_stale_remote_push | Two local independent clones and shared bare remote reject stale push; authenticated provider path not proven. |
| C13 | PASS | test_malformed_identity_and_payload_fail_closed | invalid writer/session identity rejects mutation |
| P01 | PASS | test_csv_is_canonical_and_restart_readable | legacy three-column CSV persists and reads; unknown glyph separately checked |
| P02 | PARTIAL | test_explicit_state_refresh_upgrades_csv_and_preserves_snapshot | two-row five-column refresh/readback; zero/one cardinalities not executed |
| P03 | PASS | test_explicit_state_refresh_upgrades_csv_and_preserves_snapshot | proven absent records projected not_started with null revision |
| P04 | PASS | test_explicit_state_refresh_upgrades_csv_and_preserves_snapshot | existing active record projected with revision 0 |
| P05 | PASS | test_malformed_cached_state_is_rejected | malformed/unknown status rejected |
| P06 | PARTIAL | test_explicit_state_refresh_upgrades_csv_and_preserves_snapshot | mixed revision values read; interleaving snapshot not proven |
| P07 | PASS | test_explicit_state_refresh_upgrades_csv_and_preserves_snapshot | authoritative change leaves old cached state until explicit refresh |
| P08 | PASS | test_refresh_failure_does_not_mutate_csv | failed refresh leaves old CSV byte-identical |
| P09 | PARTIAL | test_stale_refresh_revision_preserves_prior_csv | stale write caught; concurrent lifecycle mutation during refresh unproven |
| P10 | PARTIAL | test_replace_uses_content_cas_and_preserves_prior_on_stale_write | stale CAS proof; two process CSV writer race not run |
| P11 | PARTIAL | test_failed_atomic_replace_preserves_prior_record | generic atomic store failure tested, not injected CSV publication/readback |
| P12 | PARTIAL | test_divergent_title_uses_provider_authority | provider title conflict resolved, lifecycle unchanged not independently asserted |
| P13 | PASS | test_default_graph_reads_saved_status_and_ignores_provider_closed | provider closed does not override active cached lifecycle |
| P14 | PASS | test_non_overlapping_changes_merge_without_provider | one-sided dependency/title changes merge |
| P15 | PASS | test_divergent_status_snapshots_conflict | divergent state/revision conflict instead of last-writer-wins |
| P16 | PARTIAL | test_malformed_cached_state_is_rejected | invalid local state rejected, stale/unsupported merge-side schema not fully tested |
| P17 | PASS | test_conflicting_lifecycle_revisions_reject_stale_remote_push | Fresh independent Git clone reads same authoritative lifecycle candidate, revision and byte-identical cached five-column CSV; stale second clone cannot publish competing lifecycle/CSV. This is a local bare-remote transport test, not authenticated GitHub provider proof. |
| P18 | PARTIAL | test_invalid_cycle_fails_before_write | invalid cycle rejected before commit; duplicate/unknown ID combinations not exhaustive |
| G01 | PARTIAL | test_graph_uses_cached_states_until_explicit_refresh | normal renderer reads cached CSV; no-network assertion not explicit |
| G02 | PASS | test_graph_uses_cached_states_until_explicit_refresh | unknown state glyph before migration rather than completed |
| G03 | PASS | test_all_six_lifecycle_glyphs_render_from_csv | all six glyphs rendered from status |
| G04 | PARTIAL | test_projection_distinguishes_dependencies_and_lifecycle_states | readiness distinguished; same-state blocked/ready pair not fully isolated |
| G05 | PARTIAL | test_graph_uses_cached_states_until_explicit_refresh | six-node --current refresh/save/render PASS; zero/one display cardinalities missing |
| G06 | PARTIAL | test_default_graph_reads_saved_status_and_ignores_provider_closed | does not trust provider closed; unavailable-provider --current path not explicit |
| G07 | PASS | test_current_cli_failure_has_no_graph_output_or_partial_csv | Public --current CLI raises visible error, does not emit partial graph or mutate CSV. |
| G08 | PASS | test_graph_replacement_preserves_cached_status | title/topology replacement retains cached state |
| G09 | PASS | test_opt_in_legend_is_after_graph_and_read_only | legend opt-in and read-only output |
| G10 | PASS | test_legend_rejects_json_and_count_without_mutation | Both incompatible non-graph modes rejected with no output/CSV or lane state mutation. |
| G11 | PASS | test_legend_current_debug_and_lane_filter_preserve_lifecycle | Actual CLI --current/--legend/--debug/lane-filter composition verifies graph and stable lifecycle. |
| G12 | PARTIAL | test_formatter_controls_encoded_text_and_display_width | render width cases pass; complete layout/cartesian input matrix unproven |
| G13 | PARTIAL | test_symbols_use_one_terminal_cell | terminal-width assertion and hosted OS probes pass, accessibility under all terminals not observed |
| G14 | PARTIAL | test_projection_distinguishes_dependencies_and_lifecycle_states | state/ready separation tested; divergent current-worktree pointer unproven |
| G15 | PASS | test_repeated_current_refresh_has_identical_csv_and_lifecycle | Two unchanged refreshes have byte-identical CSV, equal revision, unchanged lifecycle. |

## Evidence and follow-up

- Original 74-row audit: https://github.com/Ma-XX-oN/RepoWorkflow/issues/583#issuecomment-6174521136; transaction-level addendum: https://github.com/Ma-XX-oN/RepoWorkflow/issues/583#issuecomment-6174579806.
- Hosted exact-source tests: https://github.com/Ma-XX-oN/RepoWorkflow/actions/runs/38648373520 and https://github.com/Ma-XX-oN/RepoWorkflow/actions/runs/38649138881; raw/provider artifact hashes and canonical readback in issue #583 comment 6180264034.
- L18/L20/T03/T08 depend on executable #109 / #577 integration/review gate evidence, not merely read-only planner tests. C12 requires authenticated shared-provider validation. P09 race requires separately executed negative test and safe owner remediation.
- Do not merge to `main`, publish stable tags, or mark DONE until every row is proven and final source/release gates pass. Historical provider-only test skips remain skips.
