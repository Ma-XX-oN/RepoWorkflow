# RWF #109 — exact-source executor acceptance ledger

Updated: 2026-10-20 22:57 EDT. Owner: existing V3 claim 6273106943.
PR: #680 (draft; no merge). Security #85/#86 remain deferred.

## Proof levels

- Unit fixtures and simulated provider transport are **not** proof of
  actual provider operations or independently authenticated stage PASS.
- GitHub Actions hosted jobs prove only the exact source they checked.
- Real Disposable-000 runs prove only their specified test-only permissions,
  source, branches, operations and recorded side effects.
- Independently owned #583 and #677 must certify their respective contracts.
- Failed/retried/UNKNOWN is not PASS; never promote incomplete source evidence.

## Acceptance matrix

| Criterion | Expected independent behaviour | Evidence | State |
|---|---|---|---|
| P01 ownership | Preserve claim/PR, no merge | #109 claim 6273106943; PR #680 | PASS |
| P02 dependencies | #103/#681/#683 certified | Closed GitHub issues | PASS |
| P03 immutable READY | Keep PRELIM SHA fixed, mutable INT separate | Disposable run 39517395210, earlier 39511297332 | PASS (test provider) |
| P04 destination claim/CAS | Only one holder, expected-old SHA | Same disposable runs | PASS (test provider) |
| P05 current policy | Read current destination, no descendant permission | done_policy_admission and acceptance tests | INCOMPLETE (live matrix) |
| P06 source ART/AIT | Current-parent independently authenticated, no invented PASS | done_stage_certification | INCOMPLETE (live provider issuer) |
| P07 MIT | Distinct PASS/FAIL/TIMEOUT, defer/restart authority | Real Disposable run 39527393835; plus fixture negatives | PARTIAL (test-only external approval; no production MIT certification) |
| P08 terminal history | Exact authenticated terminal, recovery after lost ACK | Disposable run 39517395210 | PASS (test provider) |
| P09 ref retirement | Exact #103 PRELIM and INT physical retirement, readback | Disposable run 39517395210 | PASS (test provider) |
| P10 release evidence | Separate authenticated release and integration stages | done_evidence_provider fixtures | INCOMPLETE (actual provider artifacts) |
| P11 source-to-landed | Immutable attestation, verified landed tree and inputs | Real Disposable provider 39535233722; canonical reader fixtures | PARTIAL (test-only verifiers; production authority not bound) |
| P12 lifecycle | Complete legal transitions with durable source of truth | done_completion guarded interface | INCOMPLETE (live lifecycle) |
| P13 CLI | Native rwf done patch/minor/major executable | done_cli + public_cli guarded route + done_runtime | PARTIAL (native dispatch registered; authoritative runtime injection not installed) |
| P14 queue | Competing umbrellas, per-destination serialization, recovery | live test 39528668265 PASS; bounded queue/handoff unit fixtures | PARTIAL (real contention PASS; full production queue/lifecycle not certified) |
| P15 full assembled tests | Exact current #109 plus #103/#681/#683 | Most recent assembled probe requested | INCOMPLETE until terminal run |
| P16 independent oracle | #583 74-case matrix and #677 downstream | #583 60 PASS/14 PARTIAL, #677 open | INCOMPLETE |

## Hosted source and provider anchors

- #109 prior source `3c3762fbca367423a4a5530461685cfcc2541db0`:
  run 39513674277 SUCCESS, 2,068 tests / 14 skips, focused Ubuntu/
  Windows/macOS SUCCESS.
- Prior assembled source `3c3762fb...` plus certified #103/#681/#683:
  run 39513807802 SUCCESS, 2,517 tests / 14 skips, strict v2 PASS.
- `1798e95f907dfb7c971749d70121209112b34624`: isolated provider
  run 39517395210 SUCCESS. Default Disposable-000 main unchanged, physical
  PRELIM/INT retirement and scoped cleanup verified. ART/AIT and MIT policy
  observations were TEST-ONLY fixtures and MUST NOT be promoted to #583 PASS.
- MIT deferred/resume actual provider run 39527393835 SUCCESS: external isolated
  authority, durable timeout generation 1, approved resume generation 3,
  unapproved attempt refusal, immutable PRELIM and verified cleanup; no
  production MIT issuer or proof of complete current-source executor.
- Real two-umbrella same-destination run 39528668265 SUCCESS:
  A claim generation 1, B denied while A holds it, A MIT deferred/released
  generation 2, B takes generation 3, unchanged default main. Independent
  GitHub ref lookup after cleanup returned 404 for both PRELIM refs, the
  temporary destination branch, and A's MIT defer tag. This proves a
  scoped, isolated test-only provider scenario, not automatic queue drain
  across complete lifecycle outcomes.
- Queue scheduler and handoff: new source modules and focused fixtures include
  A-complete/B-failed-handoff/C-complete, same-destination cross-umbrella
  contention, strict no-retry UNKNOWN, and exact MIT generation authorization;
  full regression/assembly pending at this ledger revision.
- Real Disposable provider promotion 39535233722 SUCCESS: tested source
  b411d215bec5c62c8a3ca3062ec8f8743f2d7299 and landed empty-context
  commit 19a1971e0ada93adf639355c489f7948a8c464c4 share tree, provider
  promotion tag created/read/idempotently retried, default main unchanged.
  Stage receipts were explicit TEST FIXTURES; GitHub API independently
  confirmed the temporary destination and promotion tag removed.
- Native CLI and runtime proof is LIMITED: public grammar and injected
  trusted-executor callback exist and have focused hosted tests. The
  default public command currently has no bound authoritative provider
  executor and safely rejects execution rather than fabricating DONE.
- Canonical landed results now have a distinct promotion relation emitted
  alongside original immutable tested SHA logs, not a synthetic landed PASS.
- Independent current source: consult PR #680 HEAD at time of verification,
  then require new exact-source hosted/full assembled and provider run receipts.
- Earlier regression 39517273059 FAIL: forged prior terminal surfaced a
  raw CoordinationError. Code/test were corrected; historical FAIL remains.

## Immediate continuation path

1. Read current PR HEAD and exact current hosted/assembled terminal results.
2. Repair any actual failures; distinguish expected embedded negative fixtures
   from the final unittest conclusion.
3. Prove current destination allow-list changes against real provider and
   same-destination multi-umbrella CAS contention.
4. Complete authenticated ART/AIT/release/MIT provider evidence, tested
   current-parent candidate, explicit MIT TIMEOUT/defer and resumed approval.
5. Complete provider-backed canonical source-to-landed results publication,
   independent lifecycle readback and native done command.
6. Supply exact source/run/artifact/readback matrix to the separate #583 owner
   for T01–T08/L08/L09/L10/L17/L18/L20. Keep #677 downstream independent.
7. Do not mark DONE, activate production, or merge without explicit authority.

## 2026-10-20 22:40 EDT continuation

- Existing #109 V3 claim and PR #680 preserved; no remote main merge.
- Exact-source assembled revision b5d4a8878a8e8b44f3310372193f1eed5fa4073f
  plus certified #103/#681/#683: hosted 39528803049 SUCCESS,
  2,640 unittest cases OK, 14 skipped; evidence type: isolated assembly.
- New canonical landed results reader (done_results_discovery.py and shared
  test_results_reader.py entrypoint) retains original testSHA and represents
  source-tested-accepted-at-destination separately, never fictitious PASS on
  merge SHA. Cross-platform focused checks SUCCESS, standalone full regression
  still requires exact HEAD revalidation.
- New append-only GitHub provider promotion adapter
  adapters/repo_host_github_done_promotion.py: unique operation-scoped Git tag,
  exact provider readback, LOST-ACK reconciliation, current destination/tree
  check, independent landing + stage verifiers. Real Disposable-000 run
  39535233722 SUCCESS; tested source and landed SHA differ while tree matches,
  replay idempotent, main unchanged and temporary refs independently absent.
  Stage issuers there are explicit test fixtures, not authoritative release.
- Native public grammar accepts rwf done patch/minor/major. done_cli.py binds
  success only to VerifiedCompletion and emits distinct deferred/failed
  outcomes. done_runtime.py composes current plan, exact READY, provider
  attempt and independently verifiable terminal/deferred/handoff records.
  Full live default CLI host adapter is NOT yet bound: current default
  refuses to execute without a trusted executor, not complete.
- done_source_identity.py rejects material content on .ci/run/.ci/rwf command
  branches, accepts only contiguous one-parent, single-marker commits with
  authenticated request proof and exact tested SHA; positive/negative focused
  hosted jobs succeeded across three OS. Full regression pending.
- Real provider integrated source-to-landed append and negative fixtures do
  NOT independently certify #583 14 outstanding lifecycle cases or #677.
- Outstanding: trusted default native runtime connection, current-source
  authenticated ART/AIT/release/MIT, provider-backed complete lifecycle and
  canonical results readback in an actual integration, full latest assembled
  hosted platform matrix, independent #583 oracle crossing and #677 conformance.

## 2026-10-21, window 15 — source-specific evidence update

- Existing claim 6273106943, PR #680 OPEN/DRAFT/UNMERGED. Main unchanged,
  no production permission or stable-tag publication.
- Authenticated ART for predecessor 13682b27baf21e6f5d1abc2620ec23a7587f13d6
  ran as GitHub Actions 39649302325: COMPLETED/SUCCESS.
  Artifact 12369625215 SHA-256
  36a432596af41f7c1ada69b20429ef32ac46a95f66691029033ee5bc746a83c5
  independently downloaded and parsed. Its successful row has exact
  testSHA/providerCandidateSHA 13682b27..., invocation 50af6c93...,
  testVersion 0.1.122-issue.109.1.3, runner github-actions,
  result succeeded, reusable true, no dirty worktree. Historical failed
  rows in the same artifact are not promoted.
- AIT for the same predecessor requested from the provider-published
  ART branch, invocation bf1e73641a3283221ab4840dbf501725e8a4e281,
  run 39651182981. Plan and nine platform jobs PASS; terminal AIT
  provider publication remained unverified at this ledger timestamp.
- Exact-source hosted predecessor 39649334956 SUCCESS, 2,378 tests,
  14 skipped, focused Ubuntu/Windows/macOS 370 each PASS. Four-branch
  assembly 39649407300 SUCCESS, 2,827 tests, 14 skipped, strict v2
  simulated transport PASS; assembled source 0ec492a92b13f68405e715ee9b7317235198dd50.
- Real Disposable-000 provider 39649470589 SUCCESS at that predecessor:
  5/5 live destination policy, PRELIM immutability, destination CAS,
  terminal, dual physical retirement, tested-source promotion,
  actual claim/release lost-ACK reconciliation and run-scoped
  canonical lifecycle Git CAS. Confirmed temporary 8/8 refs absent.
  Stage authorities there are TEST FIXTURES, NOT production issuer.
- Subsequent native proof hardening requires an externally authenticated
  shared lifecycle envelope containing the exact plan, original tested
  source SHA, operation, provider result and stable canonical-state ref.
  A bare VerifiedCompletion or release/issue/source mismatch is now
  rejected by native CLI. Release/MIT independent GitHub App Check Runs
  are bound to source, parent, issue, app, actual test inputs, expiry
  and evidence ref; an expired/check-relabelled PASS is not reusable.
- Current candidate at ledger revision:
  0862cc8694f8e5af3019c509a4a0e2a64d2a5299,
  development version 0.1.122-issue.109.1.4 (unconsumed at request).
  Runs launched: hosted 39652773372, certified assembly 39652871383,
  real Disposable-000 39652926747, authenticated ART 39653025698.
  Terminal checks are pending; preceding successful source evidence
  CANNOT be reused for this materially changed SHA.
- There is still no configured independent release/MIT App issuer,
  globally designated production canonical state branch, or default
  trusted rwf done server service. GitHub Checks API at predecessor
  candidate returned zero release/MIT check-runs. No protected
  production main/rulesets or stable release activation.
- P01-P05/P08/P09 scoped PASS (7); P06/P07/P11/P12/P13/P14 PARTIAL
  (6); P10/P15/P16 INCOMPLETE (3) until exact final candidate proofs,
  independent human issuer and independent #583/#677 handoffs.
  Historical failed runs remain failed evidence; this is NOT DONE.

### Next authorised actions

1. Verify terminal final-candidate ART, focused/full, assembled and
   Disposable-000 results, including independent cleanup.
2. Chain genuine AIT on the very same tested SHA after provider ART PASS.
3. Bind distinct independent current-parent release/MIT Check Run issuers,
   preserve missing/FAIL/TIMEOUT/UNKNOWN and durable defer semantics.
4. Install trusted native runtime and actual globally authoritative
   canonical lifecycle source, then certify all #583 remaining cases.
5. Keep #677 downstream, existing claim and PR. Do not merge or
   declare DONE until every acceptance requirement is independently proven.


## 2026-10-21, window 16 — current provider evidence and decision gates

- Existing claim 6273106943 and PR #680 remain unchanged; no protected main
  merge, production release/tag or ruleset/security activation.
- Exact previous candidate `2b6105b9015250b4478241495d1b5dab3b640bd7`,
  development version `0.1.122-issue.109.1.5`, passed standalone hosted
  39653498763 and isolated four-branch assembly 39653601949. Those runs
  certify only the named source and do not replace independent production
  ART/AIT/release/MIT authority.
- Genuine GitHub ART run 39653741550 for that candidate **FAILED** because
  `tests.test_hosted_version_identity` raised `OSError: [Errno 39]
  Directory not empty` during temporary Git directory cleanup. The run
  published `v0.1.122-issue.109.1.5-CI-FAIL`. The test fixture failure
  is evidence of a red hosted gate, not a legitimate stage PASS.
- Prior exact-source ART 39649302325 and chained AIT 39651182981 were
  both terminal SUCCESS at `13682b27...` (`.1.3`); neither may certify
  materially changed source or its current destination parent.
- The genuine GitHub provider runs at source `13682b27...` and later
  `2b6105b9...` remain scoped to Disposable-000. Real expected-old
  destination and shared lifecycle CAS, lost-ACK reconciliation, immutable
  physical retirement and scoped ref deletion were tested. Test-only
  stage/lifecycle permissions do not establish the production oracle.
- Direct GitHub App release/MIT issuer verification now checks source,
  current parent, issue, manual tester, app ID, immutable evidence digest,
  provider evidence ref, issued expiry, unchanged double-read and
  **actual unexpired time**. A trusted issuer has not been configured.
- Native `rwf done` now requires `VerifiedNativeDone`, retaining approved
  plan/release/issue and tested-source provenance, with independently
  authenticated provider terminal/retirement/promotion plus stable
  provider-shared canonical lifecycle ref. A bare `VerifiedCompletion`
  can no longer produce native DONE. The default public CLI still has
  **no production trusted executor binding** and must continue refusing.
- Independent #583 maintains its own claim, #677 its own graph/renderer
  work; neither is silently completed by #109 evidence handoffs.

### Exact-current-candidate checklist

1. Freeze one final material source and development version after code edits.
2. Certify focused Ubuntu/macOS/Windows and full hosted + four-branch assembly
   against that exact source; preserve every historical red run.
3. Require authentic GitHub ART then chained AIT on that same source,
   with independent artifact hashes, stage identity and a bound current parent.
4. Demand a distinct actual release issuer and MIT policy/tester issuer
   (including FAIL/TIMEOUT/defer), never code-generated PASS fixtures.
5. Bind an authorised production shared lifecycle ref and public native
   executor, verify source-to-landed terminal/promotion and #583 oracles.
6. Handoff exact provider/test evidence without merging, claiming #583/#677,
   publishing stable release tags or activating deferred security #85/#86.
