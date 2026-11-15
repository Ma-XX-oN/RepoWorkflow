# Single-PRELIM completion workflow

Authoritative operator-approved contract for #108/#109/#681/#683/#103/#677.
This contract supersedes conflicting two-branch, test-before-submission and
terminal-version-consumption rules. Historical contracts remain as evidence.

Functional completion uses Git repository access, actual catalogue-selected
test results, externally recorded manual results and outgoing email.
Separate authorization/evidence verifier programs and adversarial security
certification are deferred; they are not prerequisites of this workflow.
Source identity, result applicability and expected-parent CAS remain required
for correct execution.

## CI worker and outgoing mail

`.github/workflows/prelim-done.yml` consumes versioned PRELIM submissions.
Its prepare job selects the latest version and reconstructs stale inputs;
Linux, Windows and macOS workers execute remaining registered tests and
publish immutable report refs. Acceptance collects those reports, waits for
missing platform/manual results and atomically updates the expected parent,
records completion and retires the selected PRELIM. Parent advancement
schedules preparation and testing again. A waiting result retains PRELIM.

The internal `done-worker prepare|test|accept|dispatch` commands implement
those phases. A prepared JSON plan carries the exact source, parent and
relevant-input identity between jobs. Completion receipts preserve the latest
version after retirement so older submissions cannot become eligible again.

Remote integration conflicts retain the actual merge diagnostic and email
the configured user through an existing outgoing SMTP account. Configure
`SMTP_HOST`, `SMTP_PORT`, `SMTP_ENCRYPTION` (`tls`, `ssl` or `none`),
`SMTP_FROM`, `SMTP_USERNAME`, `SMTP_PASSWORD` and optionally
`RWF_NOTIFICATION_EMAIL`; the equivalent Git `sendemail.smtp*`,
`sendemail.from` and `rwf.notificationEmail` settings also work locally.
The default recipient is the source commit's author. Hosted workflows read
mail settings from repository variables and username/password from secrets.
Delivery failure is recorded in the conflict receipt; it does not change the
parent or turn the conflict into a successful completion.

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

Name branches `PRELIM-issue-N.<rest-of-version>`. The version identifies the
submission; the name contains no GUID or parent branch. The issue's
authoritative metadata determines its parent branch, and recorded source,
parent SHA and relevant inputs bind the applicable test evidence.

For each issue, the server selects only the latest version according to the
repository's version ordering, not lexical branch-name order, timestamps,
GUIDs or predecessor chains. All older versions are ignored for scheduling
and merge, even if the latest version fails; never fall back to an older one.

1. If the selected PRELIM is based on the current parent tip, reuse applicable
   passing tests already performed for that candidate at that tip. Run only
   the remaining required tests before merge.
2. If the selected PRELIM is not based on the current parent tip, copy/integrate
   it onto that exact tip before testing. Results invalidated by the changed
   source, parent or relevant inputs cannot be reused.
3. Other PRELIM versions for the same issue are historical and ignored.

Preserve historical version identities and evidence. A source change follows
the repository's version rules before testing; unchanged retries and report
commits reuse the same version. No separate INT-ATTEMPT branch type is created.

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
Manual FAIL retains the candidate version and publishes its matching local
CI-FAIL tag from the recorded tester verdict; source repair precedes the next
version preparation.

Read current destination admission policy and require all applicable tests,
MIT results and existing authority before merge. The provider write uses
expected-old destination SHA CAS. Parent advancement requires reconstruction
and revalidation, never merge-then-rollback. Conflicts preserve the parent,
record a durable owner handoff, and email the user for remote execution.
After landing, independently verify retirement, append source-to-landed
promotion, and read canonical lifecycle/results before reporting DONE.

## Shell prompt integration

The read-only `rwf manual-prompt` command prints the current `[MIT n/m]`
prefix, or nothing when no manual cases remain. It does not select a case
or record a result. Shell hooks preserve the existing prompt and process
exit status. Load a hook in the current shell; no profile is edited:

```powershell
. C:/path/to/RepoWorkflow/scripts/rwf-prompt.ps1
```

```bash
source /path/to/RepoWorkflow/scripts/rwf-prompt.bash /path/to/RepoWorkflow/repo_workflow.py
```

For Zsh, use `rwf-prompt.zsh` with the same engine argument. Loading a hook
again replaces its installation instead of nesting another progress prefix.

## Ownership and acceptance

#109 owns executor implementation and handoff. #703 independently certifies
manual negative paths; #583 consumes actual #109 execution evidence; #677
certifies the assembled result after #109/#583. Do not introduce a completion
cycle. #813 does not block #109. RED-selector repairs are deferred in #828.
Production security deployment and stable publication remain excluded.
