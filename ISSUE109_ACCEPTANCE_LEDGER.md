# RWF #109 — exact-source executor acceptance ledger

Current status (2026-10-31): NOT CERTIFIED. The October 20 matrix and
October 21 evidence below are historical checkpoints; read the latest
October 31 addenda for live current-source and provider evidence. Owner:
existing V3 claim 6273106943.
PR: #680 (draft; no merge). Security #85/#86 remain deferred.

## Current-final-candidate acceptance status (2026-10-31)

**NOT DONE.** The 16 original P01-P16 criteria remain authoritative. A
historically successful exact-source fixture is not a final-candidate PASS.
At this checkpoint **2 procedural criteria PASS** (P01 preserved ownership,
P02 closed prerequisite tickets) and **14 final-candidate criteria remain
INCOMPLETE**, including those with historically successful test-only provider
subcases. The latest documented accepted product source
`59b4d62ef2c38a5cd53cfbe03f937c27aedcbc90` is **not** the current
consolidation branch tip. No independently issued current-source release/MIT
Check Run or bound default trusted native done executor has been verified.

| State | Criteria | Evidence classification |
|---|---|---|
| PASS (procedural) | P01, P02 | PR #680 remains open/draft; #103/#108/#118/#681/#683 closed |
| INCOMPLETE final-candidate | P03-P16 | Historical isolated provider proofs and native tests do not certify this exact branch/current parent; independent release/MIT and shared authority absent in checked evidence |

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

## 2026-10-31 — continuation after CI-trigger documentation reconciliation

- Current #109 accepted-assembly branch HEAD: `f927dbff3821d91abf91a0b4a72fbe9b926e224c` at this read.
- The implemented on-demand adapter (`.github/workflows/on-demand-ci.yml`) is gated on `.ci/run` changes to `issue-*` branches. Four extra #109 verification workflows on the consolidation branch were corrected to require `.ci/run` rather than ordinary pushes or their own workflow-file change.
- The branch carries the measured test-only elimination of duplicate imported `PrelimAttemptTests` (111 unique identities versus 155 duplicate-discovery executions); prior native evidence is recorded in #109 comments, notably runs 41226128896 and 41226227895. These are earlier exact source experiments, **not** full acceptance of this branch HEAD.
- Added `tests/test_ci_invocation_trigger_contract.py` to guard the on-demand and issue-109 push path filters against returning to unrestricted push testing. An isolated two-workflow fixture passed; broadening a fixture path filter was rejected. This fixture is not full-repository CI evidence; exact-current branch native execution still pending.
- Existing native runs 41227150581 and 41227396552 checked while running: each had five of six matrix jobs successful; each full Windows regression job remained in progress at that observation. Their native workflow explicitly checks out accepted product `59b4d62ef2c38a5cd53cfbe03f937c27aedcbc90`; do not treat their completion as proof of later consolidation commits.
- Source-read of `repo_workflow/public_cli.py` confirms `handle_public(..., done_executor=None)` delegates to `execute_done_command(... trusted_executor=done_executor)`. There is no default trusted service binding at this entry point. `repo_workflow/done_cli.py` rejects a missing executor; functional native production DONE remains **INCOMPLETE**. Do not fabricate a provider authorization or treat fail-closed behavior as successful integration.
- Remaining acceptance: current exact source three-OS broad suite with genuine tested SHA; independent ART/AIT/release/MIT issuer and provider artifact/readback; trusted default done executor and globally authoritative lifecycle state; fresh current-destination CAS, full source-to-landed proof; #583 and #677 independent oracle/certification. No production merge, tag, ruleset or approval changes authorized by this note.

### 2026-10-31 — read-only live provider evidence rechecked

- Completed genuine three-OS read-only GitHub Actions run 41222111102: all Ubuntu, Windows and macOS job conclusions SUCCESS, and full job logs each include `RWF109_LIVE_PROVIDER_READ=PASS`, `main_sha=f838ae7cddaa1376b086bb146a13bfec8602b085`, `ready_count=0`, and `lease_generation=0` (provider readback at that historical event). This is concrete provider-native read-only evidence, not a write/mutation or an ART/AIT/release/MIT issuer acceptance.
- Current independent branch read shows `main=7caf528e83d1fb09e19858029456399016b0ebe1` and `issue-109-accepted-assembly-20261030=42ae54ea1e8f4bdd5ed4cafea473d85cbf51a2d4` at this read. The earlier run's main SHA differs from current main, so it cannot certify a current-parent mutation or acceptance.

### 2026-10-31 — repository-wide CI push guard completion

- The branch additionally gates `issue-699-manual-integration-assembly.yml` and `issue-703-manual-negative-probe.yml` on a changed `.ci/run` path. The four #109 historical verification workflows and ordinary on-demand workflow have the same restriction. Manual dispatch remains independent where explicitly declared.
- `tests/test_ci_invocation_trigger_contract.py` now enumerates every GitHub workflow on the checkout, requiring `.ci/run` as the only push-path selector except three named historical migration/certification workflows that have distinct explicit path filters. Unsupported/inlined event shapes fail closed. This test is registered as an invariant on **both main and the #109 consolidation branch**. Source readback confirms all existing workflow declarations conform to the defined policy. Isolated fixture compilation and positive/broadened-path/unsupported-syntax negatives PASS; no exact checkout native CI assertion from these fixture tests.
- No `.ci/run` marker modification, no deliberate CI dispatch, no protected merge or production activation occurred during trigger corrections.

### 2026-10-31 — authenticated GitHub Checks source-specific readback

- Direct provider GET `/commits/59b4d62ef2c38a5cd53cfbe03f937c27aedcbc90/check-runs` returned `total_count=6`: three focused and three full Linux/macOS/Windows checks, all terminal `success`, each `app.slug=github-actions`. This is authenticated native Actions evidence for that **older exact product source** only.
- Direct provider GET `/commits/5d4dace45f918430a1eb477f8f59d2f0c2a76b3a/check-runs` returned `total_count=6`: five terminal success, Windows full `in_progress`, all `app.slug=github-actions` at read time. Do not claim 6/6 terminal on this revision yet.
- Neither response contains `rwf-done-release` or `rwf-done-manual-test` issued by a distinct trusted App. Thus the mandatory independently authenticated release/MIT authority is **not established for either queried SHA**, even when GitHub Actions source tests PASS. These are scoped current-provider observations, not a global proof that no issuer exists anywhere.
- The committed `.repoworkflow/validation/testResults-109.jsonl` on this branch contains only a historical non-reusable failed regression row for source `09b08dca18c98d0ba0ffa63c23bc4607ad3e0561`; do not upgrade old Actions checks into a fabricated current canonical PASS.

### 2026-10-31 — owner PR and canonical-authority scope

- Direct current GitHub PR #680 read: `open`, `draft=true`, head branch
  `issue-109-done-executor-v1` at `95e5a55d7d9bb16d93a98e517c48e59b43589913`, base
  `issue-103-prelim-retirement-v1`. This is **not** the newer
  `issue-109-accepted-assembly-20261030` consolidation branch. Neither
  PR head nor accepted assembly is a certified final production merge.
- Enumerated 828 branch names from GitHub's branch API and found no branch
  explicitly named as a designated production canonical shared lifecycle
  authority. This naming scan does not prove that no authority exists under
  an arbitrary other name. The actual live default CLI still supplies no
  trusted executor and the shared-lifecycle provider requires the caller to
  designate its authoritative branch.

### 2026-10-31 — Disposable-000 independent namespace inventory

- Direct current provider read: Disposable-000 `main` SHA is
  `b411d215bec5c62c8a3ca3062ec8f8743f2d7299`.
  `refs/heads/INT-ATTEMPT-*` inventory is empty. The PRELIM prefix has
  **three** existing refs: `PRELIM-issue-123/main-44444444-4444-4444-8444-444444444444`,
  `PRELIM-issue-703/issue-703-live-destination-20261022t1627-11111111-1111-4111-8111-111111111703`, and
  `PRELIM-issue-703/issue-703-timeout-destination-20261022t1636-22222222-2222-4222-8222-222222222703`.
- No proof that those refs belong to an unfinished #109 run or should be
  deleted. They are not the run-scoped refs named in #703's October 31
  cleanup handoffs. Preserve their ownership and do not treat an empty
  `INT-ATTEMPT-*` inventory as proof of complete global cleanup.

### 2026-10-31 — corrected native matrix exact-source binding

- The old `issue-109-accepted-assembly-native.yml` attached six checks to an
  invocation push while checking out hardcoded accepted source
  `59b4d62ef2c38a5cd53cfbe03f937c27aedcbc90`, regardless of newer
  consolidation changes. Thus run 41227150581/41227396552 checks cannot
  certify their triggering `head_sha` revisions even after completion.
- Corrected the workflow on the consolidation branch: a read-only Ubuntu
  `plan` job calls existing authoritative
  `scripts/on-demand-ci-plan.py` to verify the dedicated `.ci/run`
  invocation, derive `tested_sha` and `stage`, and validate SHA shape.
  Focused and full Linux/macOS/Windows jobs now depend on `plan`, check out
  exactly `needs.plan.outputs.tested_sha`, assert their actual HEAD equals
  it, and run only on regression/integration stages. RED/temporary/GREEN
  marker requests do not start those broad native matrices.
- Exact committed workflow Git blob `a9764ce30c738ac83d4dae904c881d1d98da7f26`
  matched locally reproduced workflow bytes. YAML parser and matrix/path
  assertions PASS. Extracted exact embedded Python compiled and produced the
  correct outputs for all five declared stages, rejecting an invalid SHA.
  These are static and isolated execution checks, **not a live Actions run**.
- No `.ci/run` change was made and no new broad native run requested. A
  fresh correct exact-candidate native run remains required after the final
  functional candidate is frozen and independent authorities are available.

### 2026-10-31 — exact-code on-demand plan real Git fixture

- Verified exact module bytes by Git blob identity: GitHub branch
  `repo_workflow/ci_invocation.py` blob `3d22ab5bac025c0fe7cf69b96492dfcc1e5508c3`
  and `scripts/on-demand-ci-plan.py` blob
  `5277f1cb15820b4043896bc77041878f9ce35b82` each matched a local
  materialized copy. Both modules passed `py_compile`.
- An isolated actual Git repository executed the **exact copied code**:
  dedicated regression invocation PASS with tested source SHA equal to prior
  branch tip; repeated marker retry PASS while recovering the original source;
  ordinary source-only commit rejected; forged previous-tip SHA rejected.
  No provider invocation and no hosted CI run were started. This is a narrow
  local exact-code real-Git test, not full checkout/3OS certification.
- The native workflow exact YAML blob `a9764ce30c738ac83d4dae904c881d1d98da7f26`
  was parsed locally and its embedded Python stage-output checks passed all
  five stages and invalid-source rejection. Subsequent cosmetic job-label
  revision does not change its plan or source checkout semantics.

### 2026-10-31 — committed CI marker exact-byte validation bug fixed

- Verified bug in shared `repo_workflow/ci_invocation.py`: helper `_git()` stripped `git show HEAD:.ci/run` output before `parse_invocation`, allowing a committed `.ci/run` with an extra trailing blank line to pass the strict one-marker grammar. The malformed committed marker was reproduced using the exact old GitHub source in an actual isolated Git fixture.
- Fixed on both `main` and the #109 assembly branch: `_git(...,raw=True)` preserves committed marker content for both current `verify_invocation` and historical `original_candidate`; ordinary command-line Git identity reads retain whitespace trimming. Fixed source Git blob `bcc7e44351aa5a15e75fe44281166e80255511de`, verified identical on both branches.
- Added `test_committed_marker_extra_blank_line_fails_closed` to `tests/test_ci_invocation.py` on both branches. Exact test Git blob `0e6c3d76ea54f99c9f032e53d667e44c5b100c3d`, verified identical on both.
- Source and test Python compilation PASS. Executed exact Git-blob-identical source and test files in isolated real Git fixture with `python -m unittest discover -s ... -p test_ci_invocation.py`: **9/9 PASS**. Additional exact-code marker checks included valid dedicated invocation/retry and negative ordinary source-only, forged parent SHA, extra newline and malformed contents. This is an isolated exact-source verification, not a full checkout or three-OS native run.
- No `.ci/run` commit, hosted CI dispatch, production branch merge, or independently issued release/MIT authorization was produced by this bug fix.

### 2026-10-31 — CRLF exact-byte bypass fixed and verified

- After stripping the extra-blank-line vulnerability, a separate real-Git fixture reproduced acceptance of a single committed CRLF suffix `\r\n`: `subprocess.run(text=True)` performed universal-newline translation before strict parsing. This violates the canonical no-suffix-or-single-LF request grammar.
- Corrected raw marker Git reads to use subprocess binary capture and strict UTF-8 decoding; ordinary Git metadata reads remain text-mode/trimmed. Both current committed and historical invocation marker paths use raw byte-preserving reads. Non-UTF-8 marker data now fails closed.
- Added real-Git `test_committed_marker_crlf_fails_closed` alongside the extra-blank-line regression. **10/10 exact-code isolated real-Git tests PASS**, Python compilation PASS, after correction.
- Verified byte identity across `main` and #109 assembly: `repo_workflow/ci_invocation.py` Git blob `30f4e0d243972a81a6d124beab21a75eab112780`; `tests/test_ci_invocation.py` blob `591baa145a74e20fde15d621223c100d7bdbad68`. Local `git hash-object` of tested source equals GitHub blob hashes.
- Source/fixture acceptance is not an actual three-OS CI test or production provider-stage certification. No `.ci/run` invocation or production integration was initiated.

### 2026-10-31 — historical invocation retry strictness

- Added a real-Git historical-chain negative test, `test_historical_retry_rejects_noncanonical_marker`. A valid new request referencing an earlier malformed CRLF request is correctly recognized as a request, but `original_candidate` refuses to traverse the malformed historical marker as valid test-source identity.
- Exact tested source module remains blob `30f4e0d243972a81a6d124beab21a75eab112780`. Added regression tests bring the **exact-source isolated real-Git suite to 11/11 PASS**, including current and historical CRLF, extra blank line, dedicated retry, forged parent and mixed source rejection. The exact tested test module blob `ef817bbc68a9bf8ff7dafbfab5da00af8c7c17f1` was independently read back from **both main and #109 assembly** and matches local `git hash-object`.
- No current three-platform CI acceptance or independent release/MIT App issuance is implied by these focused local tests.

### 2026-10-31 — strict UTF-8 negative completion

- Added `test_committed_marker_non_utf8_fails_closed` with an actual Git commit containing a non-UTF-8 byte. The exact committed marker reader rejected it. **12/12 focused exact-source real-Git tests PASS**; both source and test modules compiled successfully. Current source blob remains `30f4e0d243972a81a6d124beab21a75eab112780`; current test blob `8c1d39a5dcacff850240e09ac85c27f92e4fbc5e` matches locally executed source and both GitHub branches.
