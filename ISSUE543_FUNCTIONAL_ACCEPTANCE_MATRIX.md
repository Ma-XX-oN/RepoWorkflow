# Issue #543 — functional acceptance ledger (V3)

## Exact revision and evidence boundary

- Repository: `Ma-XX-oN/RepoWorkflow`; current integration PR [#567](https://github.com/Ma-XX-oN/RepoWorkflow/pull/567).
- Original lane audit base: `dcdaea2db881b4075cbd87ab9d225d5fe8ae4bf2`.
- Final functional implementation source: `e47cfd2dd5a3598f748bb8e9be4414858e490fdb` (hosted tested).
- Final invocation `09559dc16d6c608c7afe017cae10c653832a3d60`; successful publication commit `741d24190bff50855921225d1f689f4aaebebd25`.
- Hosted final integration run `38114398190`: 1,118 tests PASS, 9/9 Ubuntu/Windows/macOS jobs PASS; immutable artifact `11692917496`.
- Hosted regression `38114405143`: 1,118 tests PASS, artifact `11692588205`. GREEN `38114696089` and reused retry `38114733164`. RED `38114648490` uses a derived fixture commit with the same implementation; temporary `38114658271` similarly.
- Historical runs on different source revisions are contextual evidence only, never final exact-source certification.
- #85 protected-main and production controls are **SECURITY-DEFERRED**, not functionally accepted. No merge, release tag, or production activation authorised.

## Independent acceptance matrix

| ID | Requirement | Status | Evidence / outstanding work |
|---|---|---|---|
| M01 | Six public test families and spelling | **PASS** | Six public stage CLI probes, local #629 tests. |
| M02 | Single persisted RED selection; zero one many invalid | **PASS** | Committed RED/GREEN selection tamper/deletion regressions, final source. |
| M03 | Stage help and --remote option grammar | **PASS** | Stage help and --remote grammar probes; Bash double-tab timing regression. |
| M04 | Superseded validate commands absent | **PASS** | Legacy validate commands rejected by CLI tests. |
| M05 | Dedicated marker stage and pre-invocation tip | **PASS** | Committed HEAD invocation marker; provider stage plan success. |
| M06 | Missed invocation retry binds immediate previous tip | **PASS** | GREEN retry 38114733164; temporary retry 38114232821, both exact-source-bound. |
| M07 | No paid testing on ordinary push | **INCOMPLETE** | No complete independently verified ordinary-push negative provider event ledger. |
| M08 | Remote results reading triggers no new run | **PASS** | Hosted validate jobs ran read-only remote-results retrieval. |
| M09 | Local and hosted stages select equivalent tests | **INCOMPLETE** | Positive hosted stages pass; exhaustive local/hosted selection equivalence outstanding. |
| M10 | Canonical per-issue testing log write | **PASS** | Canonical per-issue JSONL in provider commits, immutable archives. |
| M11 | Local results reads canonical log | **PASS** | Local results parser and malformed-tail rejection tests. |
| M12 | Remote results retrieves provider records | **PASS** | Hosted remote retrieval after provider publication; verified logs. |
| M13 | No one many invalid for each stage | **INCOMPLETE** | Stage-specific no/one/many/invalid provider permutations incomplete; local probes pass. |
| M14 | Malformed or stale RED selection rejected | **PASS** | Uncommitted, deleted, malformed selection rejected against HEAD. |
| M15 | Missing selection warns and records SKIPPED not PASS | **PASS** | Never-configured RED/GREEN selection yields logged SKIPPED. |
| M16 | Temporary catalogue path and cleanup | **PASS** | Temporary groups and cleanup tested; provider 38114658271. |
| M17 | Expected RED vs unexpected exit and infrastructure failures | **PASS** | RED provider 38114648490 classified declared exit 1 as RED, no fake zero-exit. |
| M18 | Unchanged accepted GREEN PASS actually bypasses subprocess | **PASS** | GREEN first 38114696089 reused=false, retry 38114733164 reused=true; temporary retry similarly. |
| M19 | Changed inputs invalidate applicable cached evidence | **PASS** | Temporary changed-input 38114304426: two groups rerun, both reused=false. |
| M20 | Exact candidate and catalogue SHA binding | **PASS** | Provider invocation/candidate SHA and catalogue binding, retry lineage negative tests. |
| M21 | Reject failed missing stale or replayed evidence | **INCOMPLETE** | Live malformed/stale/replay provider outcome negative matrix pending. |
| M22 | Reject forged/malformed external evidence | **INCOMPLETE** | End-to-end forged external evidence rejection pending (local mock negatives pass). |
| M23 | Linux Windows and macOS hosted matrix | **PASS** | Final integration run 38114398190: 1118/1118 tests and all 9 platform jobs PASS. |
| M24 | Protected main refuses direct push bypass force delete | **SECURITY-DEFERRED** | SECURITY-DEFERRED (#85): protected-main direct push/bypass/force/delete controls. |
| M25 | Stale destination race rejects later candidate atomically | **INCOMPLETE** | Live competing-actor stale destination race negative test pending. |
| M26 | Reconcile required checks and documentation | **INCOMPLETE** | Reconciled canonical 29-row acceptance matrix and docs; required checks still require authoritative integration audit. |
| M27 | Provider immutable artifact lookup | **PASS** | Immutable artifacts for all five stages; final integration artifact 11692917496, readback verified. |
| M28 | Incomplete failed and unavailable provider outcomes | **INCOMPLETE** | Negative live unavailable/failed provider outcome test pending; local fail-closed probes pass. |
| M29 | Source-mixed request and uncommitted marker tamper | **PASS** | Source-mixed commits and uncommitted marker tampering rejected by real-Git tests. |

## Remaining functional provider work

M07 ordinary push exclusion (negative provider event evidence), M09 full local/hosted selection parity, M13 every-stage provider cardinality, M21 stale/replay outcome matrix, M22 forged external evidence refusal, M25 concurrent stale destination race, and M28 unavailable-provider failure matrix are **INCOMPLETE**. Required checks and public documentation cross-reference must still be independently audited before M26 can be considered PASS; matrix formatting itself has been repaired.

**Matrix count:** 20 PASS, 0 confirmed FAIL, 8 INCOMPLETE, 1 SECURITY-DEFERRED. Source repair of this document does not certify any outstanding provider case.
