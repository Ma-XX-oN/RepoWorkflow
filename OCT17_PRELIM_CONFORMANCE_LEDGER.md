# October 17 PRELIM Conformance Ledger — #677

Status: **INCOMPLETE**. This is a source-bound audit, **not**
certification of the revised model. No production merge or protection
activation is authorized.

## Exact evidence

| Scope | Source | Finding |
| --- | --- | --- |
| Default branch | `8625f513ec2a13e8dc712054382f04dc8b1f8bb9` | `WORKFLOW_LIFECYCLE.md`, `WORKFLOW_INTEGRATION.md`, and `TEST_STRATEGY.md` still describe `prelim-main-<GUID>`; no indexed `INT-ATTEMPT` / `allow-tickets` symbols |
| #82 / PR #667 | `958d5b61de9b83368b5fb0e759d9d648d1d631f4` | `repo_workflow/prelim_attempt.py` still constructs `prelim-main-<attempt>`; new published namespace, destination-independent parent handling, and branch-as-ready semantics are not certified |
| #83 / PR #668 | `c765458450f52770c43d41277db088bf1963b262` | New GUID on stale reintegration covered by older scoped work; applicability to new `INT-ATTEMPT` and per-destination queue **not certified** |
| #102 / PR #669 | `b24eccde438bf0110734442360456dc263b70375` | Exact PRELIM SHA validation is implemented under earlier model; new INT-ATTEMPT candidate certification is **not established** |
| #84 / PR #672 | `b9acb02b15be3a9ccc0be10d4ffa1b56cfe8a398` | `repo_workflow/prelim_integration.py` creates provider-neutral integration PR request; does not implement per-destination branch-ref queue discovery or coordinator-owned INT-ATTEMPT |
| #108 / #109 | Issue contracts as amended 2026-10-17 | Queue model was changed from transient JSON/coordination branch to published PRELIM refs; previously completed #108 code was **not** recertified |
| #103 | Issue and CSV contract | Old #85 functional blocker conflicts with deferred hard security policy |
| #109 | Issue and CSV contract | Old #86 functional blocker conflicts with deferred protected stable-tag policy |

## Convergence graph correction (PR #678)

- #103 dependencies `84;85` -> `84`; #85 stays OPEN/deferred.
- #109 dependencies `83;86;103;108;118` -> `83;103;108;118;677`; #86 stays OPEN/deferred.
- Add #677 with dependencies `83;84;102;108`.
- Parsed `.repoworkflow/tickets.csv` from the draft candidate: **270 unique
  ticket entries, zero missing dependencies, zero dependency cycles**.
- Changes are **draft/unmerged**. Current authoritative main graph is
  not yet updated by this PR.

## Test obligation matrix

| Case | Expected | Current status |
| --- | --- | --- |
| Offline independent PRELIM submissions, GUID immutable after first push | Two READY refs, no queue-marker branch or file | NOT CERTIFIED |
| Distinct umbrellas targeting same destination | One coordinator processes one integration at a time | NOT CERTIFIED |
| Non-main and RC destinations | Same coordinator with destination policy differences | NOT CERTIFIED |
| INT-ATTEMPT created from published PRELIM | New mutable server workspace, PRELIM head unchanged | NOT CERTIFIED |
| Integration with parent advanced after publication | Rebuild against current parent and recertify affected tests | NOT CERTIFIED |
| Final destination concurrent update | Exact expected-old destination SHA rejection, no wrong merge | NOT CERTIFIED |
| `allow-tickets` absent | No extra allowance restriction | NOT CERTIFIED |
| `allow-tickets` present empty | All children denied | NOT CERTIFIED |
| `allow-tickets` populated | Only listed immediate child IDs allowed | NOT CERTIFIED |
| Allowed umbrella with unlisted descendant | Descendant cannot bypass immediate parent | NOT CERTIFIED |
| Current destination policy updated after submission | Apply latest policy at actual processing | NOT CERTIFIED |
| Untrusted/invalid policy or file format | Deterministic rejection; never silently grant | NOT CERTIFIED |
| Test results / version commits in INT-ATTEMPT | Exact tested SHA/evidence identity; material changes invalidate affected evidence | NOT CERTIFIED |
| MIT TIMEOUT versus real MIT FAIL | Distinct durable recoverable states | NOT CERTIFIED |
| Provider merge response lost | Read back and reconcile; never blindly retry | NOT CERTIFIED |
| Cleanup | Preserve landed provenance, failures and deferred work | NOT CERTIFIED |
| #583 executor oracles T01-T08, L08/L09/L10/L17/L18/L20 | Real mutation-time PASS/negative provider evidence | NOT CERTIFIED |

## Dependency-complete handoff

#677 owns new-model convergence and cross-branch certification tracking,
not another developer's existing source files. #109 owns the actual mutating
executor; #103 owns post-integration cleanup. Preserve draft source PRs
#667/#668/#669/#672 and their completed historical evidence.

To change this ledger to PASS, provide exact assembled candidate, positive
and negative test results, hosted regression and integration execution, live
provider observations, issue and PR links, and explicit acceptance readback.
Security #85/#86/#676 remains deferred, not falsely reported GREEN.

## Follow-up execution evidence — 2026-10-17

The functional graph dependency correction was revised to avoid a semantic
completion cycle: #103 depends on #84; #109 depends on #83/#103/#108/#118;
#677 depends on #83/#84/#102/#108/#109 and is the *downstream*
assembled-model certification gate. Exact graph parsing on the current draft
#678 branch: 270 nodes, 0 unknown dependencies, 0 cycles.

Implementation drafts created during the 25-minute bounded run:

- PR #678: offline GUID-qualified published PRELIM discovery, strict
  destination-at-SHA admission, tests and real local Git two-satellite fixture.
- PR #679: #103 conservative landed-retirement preflight, stacked on #84.
- PR #680: #109 guarded mutation boundary, stacked on #103 and reusing #677
  source files; destination/ticket/SHA-bound admission, expected-old SHA
  passed to provider, independent landing readback, no false UNKNOWN success.

An equivalent isolated local Python harness ran **35 focused tests PASS**
including a real local Git stale-writer CAS fixture. This does NOT establish
full repository regression, GitHub provider acceptance or exact PR-head CI.
No PR-associated hosted workflow runs were returned for these new draft HEADs
by the currently available provider query. No PR merged.

**Still NOT CERTIFIED:** production CLI wiring, source-branch publication
migration from older `prelim-main-<GUID>` paths, genuine per-destination
coordination/locking, server-side PR/merge integration and CAS, authenticated
full ART/AIT/MIT execution, failed/UNKNOWN recovery and durable queue state,
remote cleanup, exact evidence promotion, complete #583 executor oracles,
assembled regression/hosted integration. #85/#86/#676 security deferred.

## 2026-10-17 continuation checkpoint

Source review revealed two mandatory functional prerequisites: #681 (draft PR #682), the v2 host adapter needed for PRELIM inventory/INT-ATTEMPT writes/coordinator CAS/terminal records; and #683 (draft PR #684), the older #82/#84 producer migration to immutable destination-qualified PRELIM submission. Both are OPEN and incomplete. The repo-host v1 six-operation adapter cannot serve the new coordinator as-is. #109 (draft PR #680) now has a provider-neutral destination CAS lease boundary and a terminal-proof exception for deliberately retired PRELIM refs; neither is wired to live provider enforcement yet. #103 remains draft PR #679.

Revised draft graph has 272 nodes and no missing links/cycles. #109 depends on #681 and #683 in addition to its functional predecessors. #677 is downstream certification. Isolated focused Python suite: 71 PASS, including current parser, queue, Git fixtures, claim/release, v2 interface/adapter mocks and producer wrapper. This is NOT hosted full regression or real provider merge proof.

Private disposable GitHub branch `rwf681-cas-20261017-1849` was created for a CAS experiment. The stale expected-SHA connector call gave a GraphQL error, not a definitive stale-ref refusal; provider CAS acceptance is INCOMPLETE. No production merge or ruleset change. #85/#86/#676 stay deferred.
