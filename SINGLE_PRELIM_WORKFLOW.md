# Single-PRELIM completion workflow

Authoritative operator-approved contract for #108/#109/#681/#683/#103/#677.
This contract supersedes conflicting two-branch, test-before-submission and
terminal-version-consumption rules. Historical contracts remain as evidence.

## Usage and outcomes

`rwf done patch|minor|major [--remote]` finishes an issue. Tests may have
been run on any branch or deferred to the server, including platform tests.
Applicable known failures prevent completion; missing tests permit submission
and must pass before merge. External manual results remain tester-supplied.

Testing-report commits do not change effective source identity. Recognize
them by verified contents and provenance, never their subjects alone.
Increment the candidate version before testing only when source changes;
report commits, unchanged retries and MIT pauses do not increment it.
Tags never move. A later failure for the same source/version replaces its
success tag with the corresponding CI-FAIL tag at that same source, keeping
the append-only test history. INCOMPLETE is not a test failure.

## PRELIM selection

The tip is the authoritative parent-branch tip. A published PRELIM is a
completion submission, not proof that all required tests have executed.

1. A latest PRELIM rooted at the current parent tip is the merge candidate.
2. A latest PRELIM rooted at an older parent tip must be copied/integrated
   onto the current parent and tested before merge.
3. An earlier PRELIM for the same issue is superseded and ignored for
   scheduling and merge. Never fall back after the latest submission fails.

Use recorded authenticated predecessor identities to establish submission
order; GUIDs, timestamps and ref enumeration are not ordering authority.
Preserve historical PRELIM identities and evidence. Reconstructed candidates
use new PRELIM identities; no separate INT-ATTEMPT branch type is created.
Multiple incomparable submissions require explicit reconciliation, not a guess.

## Execution

Verify current-source results, prepare the version if source changed, and run
remaining required catalogue-selected tests. Local completion leaves a PRELIM
submission; remote completion consumes it and runs remaining platform checks.
On stale parent, reconstruct against its exact current tip and rerun tests
whose source, parent or relevant inputs changed. Repeat version preparation
only if effective source changed. Tests are not restricted by branch name.

For pending manual cases, show `[MIT n/m]` in the shell prompt. Select the
first case with `rwf test integration --manual`, a one-based case number,
or its issue-qualified name. Return to the prompt after presenting the case.
`rwf test succeeded` records its result and advances progress;
`rwf test failed` stops testing for developer repair. Timeout is distinct
from FAIL, and an old verdict never applies to a different candidate.

Read current destination admission policy and require all applicable tests,
MIT results and existing authority before merge. The provider write uses
expected-old destination SHA CAS. Parent advancement requires reconstruction
and revalidation, never merge-then-rollback. Conflicts preserve the parent,
record a durable owner handoff, and email the user for remote execution.
After landing, independently verify retirement, append source-to-landed
promotion, and read canonical lifecycle/results before reporting DONE.

## Ownership and acceptance

#109 owns executor implementation and handoff. #703 independently certifies
manual negative paths; #583 consumes actual #109 execution evidence; #677
certifies the assembled result after #109/#583. Do not introduce a completion
cycle. #813 does not block #109. RED-selector repairs are deferred in #828.
Production security deployment and stable publication remain excluded.
