# Guarded Task-to-Release Workflow

Status: design specification for issue #14.  This document records the agreed
workflow model before implementation so the invariants do not depend on
conversation history or operator memory.

## 1. Goals

The workflow is designed primarily to prevent accidental repository damage,
not to defend against a malicious developer.  Where practical, however, remote
server rules should make unsafe transitions mechanically impossible.

The workflow must:

- keep task development, integration preparation, and stable publication
  separate;
- make guard failures authoritative STOP signals rather than repair-forward
  opportunities;
- remove literal version-number selection from normal developers/agents;
- permit complete authoritative local validation when hosted CI quota is
  unavailable;
- automatically run missing automated validation on the server after push;
- avoid re-running expensive hosted validation when exact-candidate local
  evidence is already complete;
- preserve a durable audit trail for task and integration candidates;
- ensure stable `main` and stable tags are created only through the protected
  server-side path.

## 2. Responsibility boundaries

RepoWorkflow is generic.  Consumer repositories retain repository-specific
version semantics behind a repository-owned `repo-version` adapter.

RepoWorkflow may expose user-facing forwarding commands under
`repo-workflow version ...`, but it must not learn where a consumer stores a
version or how that version is edited.

The three enforcement layers are:

1. RepoWorkflow state machine and repository-owned adapters;
2. local Git guard hooks for early mistake prevention;
3. server-side branch/tag rules for the hard remote boundary.

The same RepoWorkflow engine and consumer validation scripts must drive local
and hosted validation.

## 3. User-facing command model

Normal commands are intended to be:

```text
repo-workflow what-next
repo-workflow what-next --json

repo-workflow validate regression
repo-workflow validate integration succeeded
repo-workflow validate integration failed

repo-workflow publish-validation
repo-workflow verify-release

repo-workflow version
repo-workflow version --json
repo-workflow version task issue <number>
repo-workflow version integrate increment patch
repo-workflow version integrate increment minor
repo-workflow version release-major
```

`rwf` should be available as a concise advanced-user alias.

State transitions use positional words.  `--...` is reserved for real options,
such as changing output representation with `--json`.

Low-level consumer operations such as advancing a CI iteration or an
integration-failure generation remain available to RepoWorkflow through the
repository adapter, but are not normal user-facing commands.

## 4. `what-next` is the workflow guide rail

`repo-workflow what-next` inspects the current repository and workflow state
and reports legal next transitions plus blocked operations and reasons.

`repo-workflow what-next --json` exposes the same information in a stable
machine-readable form.  Shell completion must derive from the same state
machine rather than maintaining a second policy implementation.

For example, when an integration result is required:

```text
rwf validate integration <TAB>
```

may offer only:

```text
succeeded
failed
```

When a task is accepted but merge authorization is absent, `what-next` must
say that integration/merge is blocked rather than infer permission from GREEN
CI, a completed issue, or a ready pull request.

## 5. Version namespaces

### 5.1 Stable releases

```text
vX.Y.Z
```

- `X`: major;
- `Y`: minor;
- `Z`: patch.

A stable tag may be created only after the accepted candidate reaches the
protected **server `main`**.

Normal integration chooses only `patch` or `minor`.  The repository adapter
derives the literal next version from the current authoritative parent.

Major is reserved for the explicit major-release workflow.

### 5.2 Task versions

```text
vX.Y.Z-issue-P.Q.R
vX.Y.Z-issue-P.Q.R-CI-FAIL
```

Where:

- `P` is the issue number;
- `Q` is the number of times merge/integration/acceptance rejected the task and
  sent it back to development;
- `R` is the regression-validation iteration.

`R` is owned by `repo-workflow validate regression`.  On genuine regression
FAIL, RepoWorkflow records the failed candidate and internally asks the
consumer `repo-version` adapter to advance the CI iteration.

`Q` is owned by `repo-workflow validate integration failed`.  That transition
records the failed integration/acceptance result and internally asks the
consumer adapter to advance the merge/integration-failed generation and reset
the CI iteration.

Users should not manually manage these counters.

### 5.3 Preliminary stable candidates

```text
vX.Y.Z-PRELIM-<issue>.<integration-generation>.<validation-iteration>
```

A PRELIM tag identifies an exact proposed stable candidate before it reaches
server `main`.

PRELIM tags:

- are immutable;
- do not mean the stable release exists;
- keep exact tested commits reachable after temporary branches are deleted;
- remain useful even if final server integration is squashed;
- may point to a tree whose source already contains proposed stable `X.Y.Z`;
- never become or move to the final stable `vX.Y.Z` tag.

## 6. Task lifecycle

1. Create an `issue-*` branch from its declared parent.
2. Run `repo-workflow version task issue <number>`.
3. RepoWorkflow forwards to the repository `repo-version` adapter, which
   derives and applies the initial task version.
4. Implement the task.
5. Run `repo-workflow validate regression`.
6. On genuine regression FAIL:
   - record/tag the failed exact candidate;
   - append audit evidence;
   - advance the CI iteration through the repository adapter;
   - return to development.
7. On INCOMPLETE:
   - create no terminal PASS/FAIL tag;
   - permit retry only while the exact candidate is unchanged.
8. On PASS:
   - create the immutable successful task candidate tag;
   - proceed to required integration/acceptance testing.
9. Record integration/acceptance outcome using:
   - `repo-workflow validate integration succeeded`, or
   - `repo-workflow validate integration failed`.
10. A failed integration result advances `Q`, resets `R`, and returns the task
    to development.
11. A successful integration result marks the task accepted.
12. Acceptance does **not** authorize merge/integration.  Explicit merge or
    integration authorization remains a separate boundary.

## 7. Local `main` and ephemeral `prelim-main-<GUID>`

Local `main` is tracking state.  It should remain synchronized with the
authoritative server `main` and should not be used as a local integration
workspace.

A preliminary integration branch is not part of ordinary issue development.
Create one only when an authorized workflow is actually attempting a local
integration toward `main`.

Each integration attempt receives a newly generated GUID and uses that identity
for the lifetime of the attempt:

```text
prelim-main-<GUID>
```

The GUID identifies the integration attempt, not the worker.  A fixed shared
`prelim-main` remote ref is forbidden because concurrent workers could
otherwise overwrite, adopt, or delete one another's preliminary integration
state.

For one local integration attempt:

1. generate a new integration-attempt GUID;
2. create ephemeral `prelim-main-<GUID>` from the current authoritative
   server `main` tip;
3. associate that GUID-bearing branch with its integration workflow record;
4. merge the accepted task or umbrella result into `prelim-main-<GUID>`;
5. keep integration-specific conflict resolution, generated artifacts, and
   proposed stable version on `prelim-main-<GUID>`;
6. choose release intent with either:
   - `repo-workflow version integrate increment patch`, or
   - `repo-workflow version integrate increment minor`;
7. RepoWorkflow forwards the intent to the repository adapter, which derives
   and applies the literal stable candidate version;
8. run complete local validation if desired;
9. create immutable PRELIM tags/audit records for tested candidates;
10. push the GUID-qualified prelim candidate and create/use a distinct
    integration ticket/PR;
11. retain `prelim-main-<GUID>` while the corresponding server integration is
    pending; a push, GREEN validation result, or ready PR is not sufficient
    evidence for cleanup;
12. after observing and verifying that the corresponding integration has
    actually reached authoritative server `main`, resynchronize local
    `main` and delete the local and remote `prelim-main-<GUID>` refs;
13. a later local integration attempt generates a new GUID and creates a fresh
    `prelim-main-<GUID>` from the then-current server `main`.

RepoWorkflow must identify prelim branches through their integration workflow
records and GUIDs, not by searching for or assuming one shared `prelim-main`
branch.  One worker must never adopt, modify, or clean up another worker's
preliminary integration branch.

The local machine may construct and completely validate a proposed stable
candidate, but it does not create the stable release tag and should not bypass
the protected server integration step.

## 8. Reintegration when server `main` moves

Suppose a prelim candidate was constructed from server `main` at `A`, producing
candidate `B'`, and the server later advances `main` to `B`.

The old candidate is stale even if it was GREEN.

Do not rewrite the accepted issue branch and do not throw away
integration-specific work from `B'`.  Reintegrate by combining the new current
`main` state with the previous prelim candidate, producing a new candidate `C`.

Conceptually:

```text
A ----- B ---------------- C
 \                         /
  \------ B' -------------
```

`C` is a new physical tree and requires:

- recalculation of the proposed version from the new current parent;
- a new PRELIM identity;
- fresh exact-candidate validation;
- fresh audit evidence.

Old GREEN evidence never transfers to a changed candidate.

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
  "runner": "local|github-actions|..."
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
- `runner`: execution location/provider.

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
4. add GUID-qualified `prelim-main-<GUID>`, reintegration, PRELIM tags, and\n   the integration ticket;
5. add local Git guard hooks backed by the state machine;
6. add/enable server rules for protected `main`, exact-current validation, and
   stable-tag finalization;
7. pilot the full lifecycle in a consumer repository before broad migration.

No issue branch, GREEN result, completed task, or ready pull request authorizes
a merge by itself.  Merge remains a separate explicitly authorized operation.
