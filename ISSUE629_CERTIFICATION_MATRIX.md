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

The JSON matrix contains the exact class/method for each test.  The
paths below are test modules, not proof of live certification.

- **M01: Six public test families and spelling.
  Module: `tests/test_issue629_cli_acceptance.py`.
  Executable probe prepared; final #543 PENDING.

- **M02: Single persisted RED selection; zero one many invalid.
  Module: `tests/test_issue629_selection_acceptance.py`.
  Executable probe prepared; final #543 PENDING.

- **M03: Stage help and --remote option grammar.
  Module: `tests/test_issue629_cli_acceptance.py`.
  Executable probe prepared; final #543 PENDING.

- **M04: Superseded validate commands absent.
  Module: `tests/test_issue629_cli_acceptance.py`.
  Executable probe prepared; final #543 PENDING.

- **M05: Dedicated marker stage and pre-invocation tip.
  Module: `tests/test_issue629_invocation_acceptance.py`.
  Executable probe prepared; final #543 PENDING.

- **M06: Missed invocation retry binds immediate previous tip.
  Module: `tests/test_issue629_invocation_acceptance.py`.
  Executable probe prepared; final #543 PENDING.

- **M07: No paid testing on ordinary push.
  Module: `tests/test_issue629_pending_provider.py`.
  Provider/assembled acceptance PENDING.

- **M08: Remote results reading triggers no new run.
  Module: `tests/test_issue629_pending_provider.py`.
  Provider/assembled acceptance PENDING.

- **M09: Local and hosted stages select equivalent tests.
  Module: `tests/test_issue629_pending_provider.py`.
  Provider/assembled acceptance PENDING.

- **M10: Canonical per-issue testing log write.
  Module: `tests/test_issue629_stage_cardinality.py`.
  Executable probe prepared; final #543 PENDING.

- **M11: Local results reads canonical log.
  Module: `tests/test_issue629_stage_cardinality.py`.
  Executable probe prepared; final #543 PENDING.

- **M12: Remote results retrieves provider records.
  Module: `tests/test_issue629_pending_provider.py`.
  Provider/assembled acceptance PENDING.

- **M13: No one many invalid for each stage.
  Module: `tests/test_issue629_stage_cardinality.py`.
  Executable probe prepared; final #543 PENDING.
  Partial local coverage; live variants remain PENDING.

- **M14: Malformed or stale RED selection rejected.
  Module: `tests/test_issue629_selection_acceptance.py`.
  Executable probe prepared; final #543 PENDING.

- **M15: Missing selection warns and records SKIPPED not PASS.
  Module: `tests/test_issue629_stage_cardinality.py`.
  Executable probe prepared; final #543 PENDING.

- **M16: Temporary catalogue path and cleanup.
  Module: `tests/test_issue629_stage_cardinality.py`.
  Executable probe prepared; final #543 PENDING.

- **M17: Expected RED vs unexpected exit and infrastructure failures.
  Module: `tests/test_issue629_red_outcome.py`.
  Executable probe prepared; final #543 PENDING.

- **M18: Unchanged accepted GREEN PASS actually bypasses subprocess.
  Module: `tests/test_issue629_pending_provider.py`.
  Provider/assembled acceptance PENDING.

- **M19: Changed inputs invalidate applicable cached evidence.
  Module: `tests/test_issue629_pending_provider.py`.
  Provider/assembled acceptance PENDING.

- **M20: Exact candidate and catalogue SHA binding.
  Module: `tests/test_issue629_provider_probe.py`.
  Executable probe prepared; final #543 PENDING.

- **M21: Reject failed missing stale or replayed evidence.
  Module: `tests/test_issue629_pending_provider.py`.
  Provider/assembled acceptance PENDING.

- **M22: Reject forged/malformed external evidence.
  Module: `tests/test_issue629_pending_provider.py`.
  Provider/assembled acceptance PENDING.

- **M23: Linux Windows and macOS hosted matrix.
  Module: `tests/test_issue629_pending_provider.py`.
  Provider/assembled acceptance PENDING.

- **M24: Protected main refuses direct push bypass force delete.
  Module: `tests/test_issue629_pending_provider.py`.
  Provider/assembled acceptance PENDING.

- **M25: Stale destination race rejects later candidate atomically.
  Module: `tests/test_issue629_pending_provider.py`.
  Provider/assembled acceptance PENDING.

- **M26: Reconcile required checks and documentation.
  Module: `tests/test_issue629_pending_provider.py`.
  Provider/assembled acceptance PENDING.

- **M27: Provider immutable artifact lookup.
  Module: `tests/test_issue629_provider_probe.py`.
  Executable probe prepared; final #543 PENDING.

- **M28: Incomplete failed and unavailable provider outcomes.
  Module: `tests/test_issue629_pending_provider.py`.
  Provider/assembled acceptance PENDING.

- **M29: Source-mixed request and uncommitted marker tamper.
  Module: `tests/test_issue629_invocation_acceptance.py`.
  Executable probe prepared; final #543 PENDING.

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
