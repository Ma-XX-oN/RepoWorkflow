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

repo-workflow config
repo-workflow config get [KEY]
repo-workflow config set KEY VALUE
repo-workflow config unset KEY
repo-workflow config --json

repo-workflow pull-request
repo-workflow pull-request --json

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

Completion and normal CLI help use the same Python-owned declarative
command grammar as argument parsing.  The grammar attaches descriptions to
static commands/options and may attach a dynamic value provider to an
argument-bearing option.  The Bash adapter only renders that authoritative
projection; it does not maintain another command list.

Normal Tab completion shows candidate names.  A second Tab within one second at
the same completion point shows descriptions for static commands/options.  A
dynamic provider, such as the provider for `--group`, returns the catalogue
group names directly; both single and double Tab show those names without a
second, redundant description source.

Invalid manual commands and invalid completion attempts use the same
command-path diagnosis.  RWF preserves the literal tokens supplied by the
caller and underlines the first token where the path diverges.  It does not
invent a valid-looking completion to explain the failure.

For a state-invalid command, for example:

```text
RepoWorkflow error: transition is not legal in the current state:
  validate integration s
           ^^^^^^^^^^^

Legal transitions:
  regression required
  → validate regression
```

If the command prefix is legal but the current partial token has no legal
state-dependent completion:

```text
RepoWorkflow error: no completions available from the current state:
  validate integration s
                       ^

Legal transitions:
  integration result pending
  → validate integration failed
```

If the completion source is instead a bare value list, such as a test-group
catalogue, no workflow transition is involved and no `Legal transitions:`
block is shown:

```text
RepoWorkflow error: no completions available for:
  validate regression --group z
                              ^
```

A token that is absent from the general command grammar is reported as an
unrecognised command, again preserving and underlining exactly what the user
typed.  State names in diagnostics are human-readable phrases rather than
hyphenated internal identifiers.

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

## 9. Integration, audit, and release continuation

The remaining lifecycle contract is maintained in
[WORKFLOW_INTEGRATION.md](WORKFLOW_INTEGRATION.md).  It covers validation
audit records, local/hosted equivalence, integration intent, integration
tickets/PRs, protected server integration, stable finalization, Git guards,
immutable evidence, and implementation order.
