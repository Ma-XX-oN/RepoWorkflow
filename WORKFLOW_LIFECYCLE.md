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
repo-workflow validate regression --fast
repo-workflow validate regression --group NAME
repo-workflow validate integration
repo-workflow validate integration --automatic
repo-workflow validate integration --manual
repo-workflow validate integration --group NAME
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

Validation execution is explicit locally.  RWF does not infer that code is
ready merely because files changed or implementation activity stopped.

`validate regression` runs the complete required ART suite for the current
candidate.  `--fast` runs the repository-defined minimal fast/smoke ART set,
and `--group NAME` runs one named ART subset.  Fast/group runs are diagnostic:
they may record useful evidence, but they do not satisfy the complete ART gate
or advance the workflow to integration testing.  Only a complete required ART
PASS for the exact candidate satisfies that gate.

`validate integration` orchestrates the complete required integration test
set for the current candidate: all required AIT plus any required MIT.
`--automatic` selects only AIT, `--manual` selects only MIT, and
`--group NAME` selects a named integration subset.  Selected/partial runs are
diagnostic and do not by themselves satisfy the complete integration gate.
The complete gate becomes satisfied only when all required integration groups
for the exact candidate have authoritative PASS evidence.

AIT can be executed and have its result recorded by an automated runner.  MIT
cannot be executed automatically: when a full integration run reaches required
MIT, RWF presents/orchestrates the manual test requirement and waits for the
human result.  A server push may automatically run missing ART/AIT for the
exact pushed candidate, but it cannot manufacture required MIT evidence.

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

`R` is the automated regression/CI iteration.  It is consumed by a genuine
failure in automated regression testing (ART).  RepoWorkflow records the
failed exact candidate and internally asks the consumer `repo-version` adapter
to advance the regression-validation iteration.

`Q` is the integration/acceptance rejection generation.  A failed integration
test advances `Q` whether that integration test is automated (AIT) or manual
(MIT).  RepoWorkflow records the rejected exact candidate, asks the consumer
adapter to advance the merge/integration-failed generation, and resets `R` for
the next development candidate.

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

## 6. Task lifecycle and test classes

The workflow distinguishes three test classes.  The distinction is about what
is being tested and who supplies the result, not merely whether a test happens
to be executable by a program.

- **ART -- automated regression testing:** automated validation of the task
  candidate for regressions.  ART requires no user result entry.
- **AIT -- automated integration testing:** automated validation that the task
  works in its required integration context.  AIT requires no user result
  entry; its runner records the integration result automatically.
- **MIT -- manual integration testing:** human integration/acceptance testing
  for behaviour that cannot be established authoritatively by automated
  integration tests, such as required UI, network, security, hardware, or
  other observational acceptance.

ART failure is a regression/CI failure.  It records immutable failure evidence
for the exact candidate, advances `R`, and returns to development without
advancing `Q`.

AIT and MIT are both integration/acceptance testing.  A failed AIT or MIT
rejects the task at the integration boundary, advances `Q`, resets `R`, and
returns to development.  The difference is how the result transition occurs:

- AIT invokes the integration-result transition automatically from its runner.
- MIT waits for the human result and exposes that result transition to the
  user.

The concise integration-result commands are:

```text
repo-workflow validate integration succeeded
repo-workflow validate integration failed
```

When AIT is pending, the automated runner invokes the appropriate command
without user intervention.  When MIT is pending, the human invokes it.  The
state machine must know which integration-test class is pending because AIT
PASS may transition to required MIT, while MIT PASS completes the manual
acceptance boundary.  An integration failure from either class has the same
version consequence: `Q += 1` and `R` resets.

The task lifecycle is:

1. Create an `issue-*` branch from its declared parent.
2. Run `repo-workflow version task issue <number>`.
3. RepoWorkflow forwards to the repository `repo-version` adapter, which
   derives and applies the initial task version.
4. Implement the task.
5. When the implementation is ready for full regression validation, explicitly
   run `repo-workflow validate regression`.  Local RWF does not start ART merely
   because it guesses development is finished.
6. On ART genuine FAIL:
   - record/tag the failed exact candidate;
   - append audit evidence;
   - advance `R` through the repository adapter;
   - return to development.
7. On ART INCOMPLETE:
   - create no terminal PASS/FAIL tag;
   - permit retry only while the exact candidate is unchanged.
8. On ART PASS:
   - create the immutable successful task-candidate evidence;
   - proceed to required AIT, if any.
9. When ready for integration validation, explicitly run
   `repo-workflow validate integration` locally.  RWF runs the required AIT;
   its automated runner records `validate integration succeeded` or
   `validate integration failed` without user result entry.  If required MIT
   remains after AIT passes, the same full validation operation presents that
   manual requirement and waits for the human result.
10. On AIT FAIL:
    - record the integration rejection for the exact candidate;
    - append audit evidence;
    - advance `Q`;
    - reset `R`;
    - return to development.
11. On AIT INCOMPLETE:
    - create no terminal PASS/FAIL result for that stage;
    - permit retry only while the exact candidate is unchanged.
12. On AIT PASS:
    - proceed to required MIT, if any;
    - if no MIT is required, the task's integration/acceptance requirement is
      complete.
13. Run MIT only when the repository/task declares a manual integration
    requirement.  The human records `validate integration succeeded` or
    `validate integration failed`.
14. On MIT FAIL:
    - record the manual integration rejection;
    - advance `Q`;
    - reset `R`;
    - return to development.
15. On MIT PASS, mark the required manual acceptance complete.
16. The task is accepted only after every required ART, AIT, and MIT stage for
    the exact candidate has succeeded.  A repository with no required MIT does
    not invent a user test stage.
17. Acceptance does **not** itself authorize merge/integration in consumer
    repositories.  Merge authorization remains a separate repository policy
    boundary unless that repository has an explicit exception.

The same test classes apply again to a newly constructed preliminary
integration candidate.  Merging/reconciling an accepted task with the current
parent creates a new physical tree, so prior task-candidate evidence cannot by
itself validate the integrated result.  The prelim candidate must run the
required ART and then its required AIT/MIT against that exact integrated SHA.
Only that accepted integrated candidate may proceed toward protected server
`main`.

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
8. explicitly run full regression/integration validation on the exact
   integrated candidate when validating locally; complete authoritative local
   evidence may satisfy these stages, otherwise a later server push runs
   missing automated ART/AIT while any required MIT remains a human acceptance
   boundary;
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
