# Integration, Audit, and Release Lifecycle

## 9. Validation audit trail

The initial storage proposal is one append-only JSONL file per issue:

```text
.repoworkflow/validation/testResults-<issue#>.jsonl
```

Using one file per issue reduces cross-issue merge contention while `kind`
distinguishes regression from integration/acceptance events.

A record should contain at least:

```json
{
  "timestamp": "...",
  "kind": "regression|integration",
  "baseVersion": "...",
  "branch": "...",
  "testVersion": "...",
  "testSHA": "...",
  "candidateTag": "...",
  "result": "succeeded|failed|incomplete",
  "runner": "local|github-actions|...",
  "platform": {
    "os": "...",
    "architecture": "...",
    "runtime": "..."
  },
  "hardware": null
}
```

Field meanings:

- `timestamp`: when the validation result was established;
- `kind`: regression or integration/acceptance;
- `baseVersion`: parent/stable version from which the candidate descends;
- `branch`: semantic identity, retained even if the branch is later deleted;
- `testVersion`: repository version present in the tested candidate;
- `testSHA`: exact physical candidate tested;
- `candidateTag`: durable Git ref where one exists;
- `result`: authoritative outcome;
- `runner`: execution location/provider;
- `platform`: reproducibility-relevant software platform, including at least OS
  and architecture plus the relevant runtime/toolchain identity where the
  validator declares one;
- `hardware`: normally `null`; when a validator declares hardware-sensitive
  evidence, a structured object containing only the capabilities/specifications
  needed to interpret or reproduce that validation.

`platform` is part of the core audit record because otherwise evidence from
materially different operating systems or architectures can become
indistinguishable.  Platform matching requirements belong to the validation
contract: recording a platform does not imply that every suite must run on
all platforms.

Hardware collection is deliberately **test-declared and data-minimized**, not
an automatic machine inventory.  A hardware-sensitive validator may record
facts such as CPU architecture/features, GPU model/API, accelerator class, or
another capability that affects the test result.  It must not collect serial
numbers, hostnames, MAC/network addresses, device IDs, account identifiers, or
other machine-unique values merely for audit convenience.  Validators that do
not need hardware information leave `hardware` as `null`.

Do not add redundant fields merely because they are convenient when equivalent
facts can be derived from the tested commit.  A separate `suite` field is not
required initially because the test definitions normally live in `testSHA`.

If same-issue JSONL merge handling is automated, correctness must not depend on
GitHub having a locally configured custom merge driver.  A local union/custom
driver may be an ergonomic aid, not the remote source of correctness.

## 10. Local and hosted validation equivalence

A pushed candidate must automatically receive server-side examination.

The server first inspects authoritative validation evidence for the exact
pushed candidate.

- If complete acceptable local evidence exists for the exact SHA, hosted CI
  verifies/reuses that evidence and avoids re-running expensive validation.
- If required automated evidence is missing, hosted CI runs the missing work
  automatically.
- Evidence for one SHA never satisfies a different SHA.

This permits repositories with limited CI credits to perform expensive complete
validation locally while retaining server-side enforcement.

Local execution is a first-class authoritative path, not an approximation of
GitHub Actions.

## 11. Integration request/version intent

Version intent that cannot be reconstructed from Git must travel with the
candidate in repository workflow state, for example a minimal request recording
`patch` or `minor` integration intent.

Persist decisions; derive facts.

The workflow should not persist branch names, base SHAs, current versions, or
new literal versions merely when Git and the repository adapter can derive
them reliably.

Server validation independently checks that:

- the candidate still descends from/currently matches the allowed parent;
- requested increment intent is legal;
- the consumer adapter derives the same literal version as the candidate;
- the candidate version was not manually changed into an inconsistent state.

## 12. Integration ticket/PR

Task and integration claims are distinct.

The task issue/PR says that the implementation solves the task and passed task
validation.

The integration ticket/PR says that the accepted task, combined with a
particular current parent state, is a valid proposed stable state.

Server rules should reject direct task/issue integration into stable `main` and
permit only the controlled preliminary-integration path.

Pull-request use is repository policy, configured as `required`, `allowed`, or
`disabled`.  `repo-workflow pull-request` is the state-aware operation for
creating/reconciling the appropriate task or integration PR.  It derives the
head/base and workflow metadata rather than requiring callers to reproduce
policy.  `what-next` and completion expose it only when legal, and required-PR
mode blocks transitions that would bypass the PR boundary.  PR creation itself
never implies validation, acceptance, currency, or merge authorization.

## 13. Protected server integration

The remote server is the hard boundary.

Required protections include:

- protect `main`;
- require the controlled integration/PR path;
- require exact-candidate validation;
- require the candidate to remain current with server `main`;
- block direct pushes;
- block force pushes;
- block deletion;
- prevent ordinary actors/tools from bypassing the rules;
- protect stable tags from arbitrary creation, update, or deletion.

Where native merge queue support is unavailable, strict required checks and a
current-base requirement must ensure that a candidate tested against an older
`main` cannot merge after `main` advances.

A guard failure is an authoritative STOP signal.  Do not merge first and repair
versions or source state afterward.

## 14. Stable finalization

Only after the accepted candidate reaches protected **server `main`** may the
stable release be finalized.

The controlled finalizer must:

1. run `repo-workflow verify-release` against the landed server-main state;
2. obtain the canonical stable version through the repository adapter;
3. verify the intended stable tag does not already exist;
4. create immutable `vX.Y.Z`;
5. never move or recycle a stable tag.

The local machine may create PRELIM and task tags according to workflow rules,
but it does not create the final stable tag before server integration.

## 15. Major releases

Normal integration exposes only patch and minor increment intent.

Major release is a separate explicit path:

```text
repo-workflow version release-major
```

The repository adapter derives the next major version by incrementing `X` and
resetting `Y` and `Z` as appropriate.  The resulting candidate still passes
through the same exact-candidate validation, stale-base protection, protected
server integration, and stable-finalization rules.

## 16. Local Git guard layer

Consumer repositories should install local hooks that call centralized
RepoWorkflow policy rather than duplicating policy in shell fragments.

Useful checks include:

- manual/direct version edits outside the repository adapter;
- deliberate local integration commits on tracking `main` instead of
  `prelim-main-<GUID>`;
- direct push to `main`;
- force/deletion hazards;
- malformed or unauthorized stable/PRELIM/task tags;
- stale prelim candidates;
- invalid branch/version combinations;
- attempted transitions that `what-next` marks blocked.

These hooks primarily prevent mistakes.  The server remains authoritative if a
clone lacks the hooks or an operator deliberately bypasses them.

## 17. Immutable evidence

Task, PRELIM, and stable tags are unique immutable refs once created.

A tag need not be an ancestor of `main` to keep its target commit reachable.
This is especially important when a PRELIM branch is deleted or the final
server integration is squashed.

Audit records preserve semantic metadata; tags preserve durable Git object
reachability.  Both are useful and serve different purposes.

## 18. Implementation order

Implementation is tracked by issue #14 and its child/related issues.

A reasonable dependency order is:

1. finalize the repository `repo-version` adapter contract and RepoWorkflow
   forwarding semantics, extending existing issue #5 rather than duplicating
   it;
2. implement the workflow state machine, `what-next`, CLI transitions, alias,
   and completion;
3. add the validation audit trail and exact-candidate local/hosted reuse;
4. add GUID-qualified `prelim-main-<GUID>`, reintegration, PRELIM tags, and
   the integration ticket;
5. add local Git guard hooks backed by the state machine;
6. add/enable server rules for protected `main`, exact-current validation, and
   stable-tag finalization;
7. pilot the full lifecycle in a consumer repository before broad migration.

For consumer repositories, no issue branch, GREEN result, completed task, or
ready pull request authorizes a merge by itself.  Merge remains a separate
explicitly authorized operation unless that repository has a documented
repository-owned exception.

RepoWorkflow itself has such an exception.  RepoWorkflow work is expected to be
fully self-tested by the implementing worker using automated, integration, Git,
and hosted validation as applicable; the user is not a required manual test
stage.  Once RepoWorkflow work satisfies its documented acceptance criteria,
all required validation and merge gates are GREEN, and no unresolved design or
external dependency remains, the implementing worker may merge that
RepoWorkflow change without waiting for separate user merge authorization.
This exception applies only to the RepoWorkflow repository and must not be
inherited by consumer repositories.

