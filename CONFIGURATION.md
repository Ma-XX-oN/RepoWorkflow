# RepoWorkflow Configuration

RepoWorkflow schema 1 keeps repository-specific facts in the consumer while the
shared engine owns lifecycle semantics, candidate bookkeeping, and invariants.

## `.ci/repoworkflow.json`

Recommended development shape:

```json
{
  "schema": 1,
  "versionCommand": ["python", "scripts/repo-version.py"],
  "repository": {
    "integrationBranch": "main",
    "authoritativeRemote": "origin"
  },
  "environments": [
    {
      "id": "linux",
      "required": true,
      "platform": "linux",
      "capabilities": ["node-22"],
      "validationCommand": ["python", "scripts/validate.py"]
    }
  ],
  "artifacts": []
}
```

Unknown fields are rejected so configuration drift fails visibly.

### `versionCommand`

`versionCommand` is the entrypoint for the repository-owned `repo-version`
adapter. RepoWorkflow owns workflow transitions; the adapter owns all details of
where the consumer stores its version and how version-bearing files are edited.

With no arguments the adapter is a read-only query. It must:

- exit zero only when the repository's version state is internally valid;
- print exactly one canonical version to stdout;
- print task versions as `x.y.z-issue.<issue>.<generation>.<iteration>`;
- print stable versions as `x.y.z`;
- leave the worktree, commit history, symbolic `HEAD`, and local Git refs
  unchanged.

RepoWorkflow invokes mutation through semantic adapter operations rather than by
supplying a literal target version. The adapter surface required by the guarded
workflow is:

```text
repo-version
repo-version task --issue <number>
repo-version task --increment CI-iteration
repo-version task --increment merge-integration-failed
repo-version integrate --increment patch
repo-version integrate --increment minor
repo-version release-major
```

The two task increment operations are workflow primitives, not normal user
commands. RepoWorkflow owns when they occur:

- a genuine regression FAIL owns `task --increment CI-iteration`;
- a failed integration/acceptance result owns
  `task --increment merge-integration-failed`.

For task versions `x.y.z-issue.P.Q.R`:

- `P` is the issue number;
- `Q` counts returns to development after failed merge/integration/acceptance;
- `R` is the regression-validation iteration.

`task --increment CI-iteration` must preserve `x.y.z`, `P`, and `Q`, and advance
`R` by exactly one. `task --increment merge-integration-failed` must preserve
the stable base and issue number, advance `Q` by exactly one, and reset `R` to
`1`.

Integration callers choose only `patch` or `minor`; the adapter derives the
literal target from the authoritative current parent. Major is available only
through the separate `release-major` transition. RepoWorkflow must never learn
consumer-specific version storage/edit details and must never pass a complete
literal version to a generic setter.

A mutation operation may change repository-owned version-bearing files and
version-dependent generated files, but it must not create commits, move
`HEAD`, or mutate Git refs. RepoWorkflow validates the resulting semantic
transition before it commits workflow bookkeeping.

Lower-level distributed commands compare the reported development version with
`.ci/run-ci-request`. The normal local `verify` path prepares that request
binding before validation.

### `repository`

`integrationBranch` is the repository's normal integration line. The value must
also agree with `.ci/branch-policy.json`.

A development candidate may not run on `integrationBranch`. RepoWorkflow rejects
that state before authoritative development validation can begin. This prevents
an issue-qualified development identity from being accepted and tagged after it
has landed on the integration line. Stable publication is the separate path for
the integration branch and requires the repository version adapter to report a
plain stable `x.y.z` version.

`authoritativeRemote` is the Git remote used for authoritative branch/tag facts.
Failure to establish remote state is not interpreted as success.

### Validation classes

RepoWorkflow distinguishes automated regression testing (ART), automated
integration testing (AIT), and optional manual integration testing (MIT).

`environments` declares ART environments. An ART environment may additionally
declare:

- `fast: true` to include it in `validate regression --fast`;
- `groups: ["name", ...]` to include it in named
  `validate regression --group NAME` subsets.

`integrationEnvironments` declares AIT environments using the same environment
shape plus optional `groups`. AIT environments may not declare `fast`.

`manualIntegrationRequired` is a boolean. When true, a complete AIT PASS leaves
the exact candidate waiting for MIT. Only then are
`validate integration succeeded` and `validate integration failed` legal
human-result transitions. When false, RepoWorkflow must not invent a manual
acceptance gate.

Bare `validate regression` is the complete ART gate. `--fast` and
`--group` are diagnostic subsets and never advance that complete gate.

Bare `validate integration` runs the complete required AIT set. The
`--automatic` selector is the explicit AIT-only spelling; `--group NAME`
runs only that AIT subset. Subset runs are diagnostic and cannot satisfy omitted
required AIT. `--manual` is valid only when complete AIT has passed and MIT is
actually required.

### `environments`

Each genuinely distinct required execution environment has one entry and one
repository-owned `validationCommand`. Test-level fan-out belongs inside that
command, not in this JSON.

Fields:

- `id`: unique environment identifier;
- `required`: defaults to `true`;
- `platform`: `any`, `linux`, `windows`, or `macos`;
- `capabilities`: declarative capability labels;
- `validationCommand`: the single authoritative repository validation command.

The GitHub adapter projects numeric `node-<version>` and `python-<version>`
capabilities into `actions/setup-node` and `actions/setup-python` respectively.
For example, `node-22` selects Node 22 and `python-3.13` selects Python 3.13.
Conflicting versions for the same projected toolchain are rejected rather than
silently choosing one. When no Python capability is declared, GitHub uses
Python 3.13 for the RepoWorkflow engine and repository command. Other capability
labels remain declarative requirements of the selected runner and repository
validation command; the shared adapter does not pretend to provision
capabilities it does not understand.

Validation exit codes are:

- `0`: PASS;
- `1` or another non-zero code except `2`: genuine FAIL;
- `2`: INCOMPLETE because the required result could not be established.

A validation command must not modify the candidate worktree, commit history,
symbolic `HEAD` target, or local Git refs. RepoWorkflow records the violation,
restores the known-clean candidate state, and continues independent validation
where possible.

### Validation classes: ART, AIT, and MIT

`environments` declares **ART** (automated regression testing)
environments.  Each ART environment may additionally declare:

- `fast: true` to include it in `validate regression --fast`;
- `groups: ["name", ...]` to include it in one or more named diagnostic
  subsets used by `validate regression --group NAME`.

Bare `validate regression` remains the complete ART gate.  Fast and group
runs are diagnostic subsets: PASS from a subset does not satisfy the complete
ART gate.  ART FAIL advances only the regression iteration `R`; ART
INCOMPLETE leaves the exact candidate retryable without creating terminal
evidence.

`integrationEnvironments` declares **AIT** (automated integration testing)
environments.  They use the same environment shape as ART, including optional
`groups`, except `fast` is invalid for AIT.  Bare
`validate integration` and `validate integration --automatic` run the
complete required AIT set.  `validate integration --group NAME` is a
diagnostic subset and cannot satisfy omitted required AIT.

AIT records its own result.  AIT FAIL is an integration rejection and advances
`Q` while resetting `R` to 1.  AIT INCOMPLETE leaves the unchanged exact
candidate retryable.  AIT PASS proceeds directly toward authorization unless
manual integration testing is declared.

`manualIntegrationRequired` is a boolean, defaulting to `false`.  When
`true`, successful AIT exposes **MIT** (manual integration testing) result
transitions:

```text
rwf validate integration succeeded
rwf validate integration failed
```

`rwf validate integration --manual` checks that MIT is actually pending and
prints the required result choices without recording a result.  RWF never
fabricates a manual gate when `manualIntegrationRequired` is false.  MIT
FAIL has the same version consequence as AIT FAIL: advance `Q`, reset `R`,
and return to development.

ART, AIT, and MIT state is bound to the exact candidate SHA through the local
workflow-state cache.  A changed candidate does not inherit the prior
candidate's completed validation-class state.

### `artifacts`

Repositories with committed generated artifacts may declare them. The artifact
mechanism is intentionally only for committed generated artifacts; a
`committed: false` declaration is rejected. Each artifact has:

- unique `id`;
- `generatorCommand`;
- a different, independent `verifierCommand`;
- non-empty `outputs` allow-list;
- optional `platform` and `capabilities` declarations.

Numeric Node/Python artifact capabilities use the same GitHub projection rules
as validation environments so the preparation job runs the generator and
verifier under the declared toolchains.

Generation may change only declared outputs. Verification must be read-only.
RepoWorkflow rejects generator/verifier worktree, history, symbolic-HEAD, or
local-ref mutation outside the authorized generated-output commit. A failed or
incomplete artifact gate is recorded with the same candidate identity used by
the validation matrix and participates in terminal result aggregation.

The full local `verify` path materializes and commits successful declared
artifact changes using the same allow-list safeguards before validating the new
candidate. Failed/incomplete artifact-script side effects are rolled back to
the previously established clean candidate before independent validation
continues.

## Local `verify` bookkeeping

`python RepoWorkflow/repo_workflow.py verify` requires a clean named issue branch
but does not require the caller to manually prepare RepoWorkflow bookkeeping.
The command:

1. reads the repository's development version through the adapter;
2. checks authoritative terminal-tag state;
3. if the current task iteration is already consumed, invokes
   `repo-version task --increment CI-iteration` and verifies exactly one
   iteration advance;
4. refreshes `.ci/run-ci-request` after ordinary source commits when necessary;
5. commits only the bookkeeping/version changes it performed;
6. validates that prepared candidate through the normal guard;
7. runs required validation; and
8. automatically creates the PASS or FAIL terminal tag.

INCOMPLETE produces no terminal tag. `--push` pushes generated bookkeeping or
artifact commits and the terminal tag to `authoritativeRemote`. Candidate
preparation is rolled back if the adapter transition, bookkeeping commit, or
guard fails.

## `.ci/github.json`

This file contains GitHub-only runner mapping rather than repository validation
logic:

```json
{
  "schema": 1,
  "prepareRunner": "ubuntu-latest",
  "runners": {
    "linux": "ubuntu-latest",
    "windows": "windows-latest"
  }
}
```

Every configured environment must have exactly one runner mapping, and stale
runner mappings are rejected. Runtime requirements remain in
`.ci/repoworkflow.json`; `github.json` only says which GitHub machines host
those declared environments and artifact preparation.

During a consumer migration, `github.json` may additionally contain an explicit
`migrationWorkflows` array. Each entry must be the direct filename of an
existing `.github/workflows/*.yml` or `*.yaml` workflow other than `ci.yml`.
Duplicates, nested paths, non-YAML files, and `ci.yml` are rejected. The normal
policy remains closed: every additional workflow must be named in this array,
and the canonical `ci.yml` must still match the pinned RepoWorkflow template
byte-for-byte. This field exists only to keep a legacy hosted path executable
while causal equivalence is being demonstrated; remove the legacy workflow and
its entry after equivalence is established.

## `.ci/branch-policy.json`

The branch policy declares intended ancestry. Schema 1 provides:

- `integrationBranch`;
- exact `branches` rules;
- optional ordered `patterns` rules;
- per-rule `parent`;
- `allowedDependencies`;
- `umbrella`;
- `integrationTarget`.

RepoWorkflow refreshes authoritative remote ancestry before evaluating the branch.
Unmatched non-integration branches are rejected.

## `.ci/run-ci-request`

This file contains exactly the requested development version. It remains the
universal exact-candidate guard for distributed/lower-level execution. GitHub
additionally treats a modification of this file, or an explicit manual dispatch,
as the request to spend remote CI resources.

During normal local authoritative `verify`, RepoWorkflow owns refreshing this
file and places the bookkeeping commit after ordinary source commits. After that
request commit, only declared committed generated-artifact paths may change
before the tested candidate. The guard still rejects post-request ordinary source
changes when encountered outside the normal preparation path.

## GitHub adapter

A consumer's `.github/workflows/ci.yml` must match
`RepoWorkflow/templates/github/ci.yml` byte-for-byte. Product-specific commands
or policy do not belong in that YAML. During a documented migration window,
only workflows explicitly named by `migrationWorkflows` may coexist with that
canonical adapter.