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
