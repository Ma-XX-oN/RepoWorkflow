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
