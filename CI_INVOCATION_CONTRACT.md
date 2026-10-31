# On-demand CI invocation contract

Status: on-demand issue-branch invocation implemented in `.github/workflows/on-demand-ci.yml`; separate Self CI and protected production integration remain independent.

The implemented workflow triggers on `push` to `issue-*` branches with a
`paths` filter matching only `.ci/run`. An ordinary source-only push or merge
without a `.ci/run` change does not trigger this workflow. Other CI workflows
have their own triggers. Issue #538 originally documented the design only;
its historical status does not describe the present implementation.

## 1. Single invocation file

Use one tracked file, `.ci/run`. Its contents are exactly one testing
stage followed by one space and the full commit SHA at the branch tip
**before** the CI-invocation commit is made:

```text
<stage> <pre-invocation-branch-tip-SHA>
```

Allowed stages:

- `RED-testing`
- `temp-testing`
- `GREEN-testing`
- `regression-testing`
- `integration-testing`

There is no `no-CI-invocation` state. The file remains unchanged during
ordinary source-code pushes. Changing `.ci/run` in a dedicated commit and
push constitutes an explicit request for hosted validation. The stage
determines which catalogue or integration-validation operation is requested;
stage-to-runner mappings must obey the authoritative validation contracts.

The referenced SHA is **not** the SHA of the invocation commit. A commit
cannot ordinarily contain its own SHA in a tracked file. The marker records
the branch's current tip at the moment the request is constructed.

For a repeat attempt after an invocation event was missed, use the then-current
tip: this may be the commit that contained the previous, unexecuted
invocation. Thus the file contents change even when no source code changes.
Do not require a reset-to-no-CI commit or invent another invocation counter.

Example:

```text
development tip A
.ci/run = regression-testing A  -> commit B, push invocation
event missed; branch tip B
.ci/run = regression-testing B  -> commit C, push retry
```

Here A, B, and C stand for actual full Git commit SHAs. The two marker
values mean the tips immediately before each invocation commit, not the
tested candidate identity.


### Exact committed marker validation

The stage marker parser validates **the committed file content**, not a
whitespace-trimmed or newline-normalized rendition of Git output.
The accepted byte content is the canonical UTF-8
`<stage> <40-lowercase-hex-pre-invocation-SHA>` followed by **zero or one
LF** (`\\n`). Extra lines, trailing spaces, CRLF, non-UTF-8 bytes, and
forged preceding commit SHA must fail closed. This also applies when
traversing historical invocation/retry commits to recover the original
tested source. The regression tests in `tests/test_ci_invocation.py`
exercise both current and historical reads using real Git commits.

## 2. Hosted execution without a dispatcher on routine pushes

The implemented on-demand GitHub Actions push trigger uses a path filter confined to
`.ci/run`. Ordinary pushes with no change to that path must not launch a
hosted test job merely to inspect a request. CI is requested by a
selector-changing push, not automatically by every code push.

A path filter matches **changed paths in the push**, not the existence of
`.ci/run` in the checkout. A dedicated selector-changing push minimises
the risk of GitHub diff/path-filter limits masking that event. It does not
guarantee delivery: a missed event is retried with a new marker as above.

No host runner is needed just to transition back to an idle selector: no
such transition exists. Repeated requests use the new branch-tip SHA.

## 3. Request marker versus test evidence

`.ci/run` is an invocation request and historical marker, not a test
result. The existing RepoWorkflow **testing log** is the evidence of which
tests actually ran and their outcomes. Do not introduce a second parallel
evidence store solely for this mechanism.

The runner must record the actual tested candidate identity in the testing
log; the marker's pre-invocation SHA must not be treated implicitly as that
identity. Results must be attributable to the exact tested revision,
selected test stage, relevant test configuration, and test execution
environment according to the existing validation-audit contracts.

Local or external execution is a first-class testing path. It can write
acceptable results through the **same** testing-log contract without
modifying `.ci/run` or consuming GitHub Actions minutes. A successful
request or a claimed PASS in an unverified file does not by itself satisfy
the protected integration gate: the verifier checks the testing log under
the repository's existing evidence validity and integrity rules.

## 4. Pre-merge verification, not post-merge retesting

Regression and integration testing of the proposed combined result occur
**before** integration to the protected target. Neither `main` nor
`prelim-main-<GUID>` should incur an automatic duplicate test run merely
because a verified candidate was merged or advanced.

For stable integration, follow `WORKFLOW_LIFECYCLE.md` and
`WORKFLOW_INTEGRATION.md`: create a GUID-qualified preliminary candidate
from the current authoritative server `main` tip; incorporate accepted
work into that candidate; and obtain applicable regression and integration
evidence for the exact proposed combined tree before attempting the
protected merge. Reuse valid exact-candidate testing-log evidence rather
than rerunning expensive tests without cause.

The integration gate must confirm that:

1. The required testing-log evidence is valid and complete for the exact
   integrated candidate.
2. The candidate was constructed from the authoritative destination tip,
   and that destination is still at that same tip at merge acceptance.
3. The applicable parent-branch and protected-server rules hold.
4. The operation is stopped **before** merging if any check fails.

When two actors prepare candidates against the same parent tip, the first
accepted merge advances the parent. The second candidate is then stale and
must be rejected before merge. The second actor must reintegrate against
the new parent tip and obtain fresh exact-candidate evidence. Do not merge
first and revert or repair afterward.

A branch containing the current parent's state can itself be the combined
candidate under test; an additional merge solely to run tests is not
required when the candidate tree already represents the exact result.
Ancestry alone does not replace the required PASS evidence in the testing
log.

## 5. Implementation and protection boundaries

The `.ci/run` on-demand trigger is implemented; the following items concern
separate legacy Self CI, evidence/security acceptance and protected integration:

- `PUBLIC_WORKFLOW.md` section 10.1 (currently assigns issue-tier checks
  to ordinary PRs and integration to `main` pushes);
- `WORKFLOW_INTEGRATION.md` section 10 (currently requires automatic server
  examination of every pushed candidate);
- the GitHub Actions workflow, `repo_workflow/self_ci.py`, test catalogue,
  and required-check/branch-protection settings;
- GitHub path-filter limitations and required-check pending behaviour;
- trusted verification of local/external testing-log evidence without
  requiring hosted test execution on every push;
- server-enforced current-base / stale-concurrent-candidate rejection.

The on-demand trigger must be tested for initial invocation, repeated same
stage, missed event retry, source-only push, selector-only push, malformed
selector, stale evidence, local/external evidence, current-base races, and
restart or re-fetch behaviour before replacing the current CI policy.


**Canonical file names:** `.ci/run` invokes on-demand hosted CI;
`.ci/run-ci-request` is distinct legacy candidate bookkeeping, not its trigger;
`.ci/rwf` is only a proposed rename. Migration markers under
`.repoworkflow/migrations/run-*` belong to separate workflows.

## Regression enforcement

The source-level CI event-filter guard is
`tests/test_ci_invocation_trigger_contract.py`, registered as
`invariant-ci-invocation-trigger` in `.ci/tests.json`. It rejects missing,
broadened or unsupported push-path declarations in the current checkout.
On-demand and issue-specific native verification workflows require only
`.ci/run`. The three separately scoped historic migration/certification
workflows (`lane-cache-routing-certification.yml`,
`native-dependency-lane-certification-v1.yml`, and
`native-dependency-migration-v1.yml`) retain their own explicit path filters.
Their exception is **not** permission to add unrestricted native testing on
ordinary pushes. Changes to a GitHub workflow event filter must be reviewed
against this guard and its authoritative contract before merging.
