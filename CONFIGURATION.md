# RepoWorkflow Configuration

RepoWorkflow schema 1 keeps repository-specific facts in the consumer while the
shared engine owns lifecycle semantics, candidate bookkeeping, and invariants.

## Consumer-root state isolation

RepoWorkflow resolves one consumer repository root for an operation.  Persistent
or checked-in data under `.repoworkflow/` is always resolved relative to that
root; nested repositories and submodules do not contribute configuration or
state.

Consequently, after initializing a consumer that pins RepoWorkflow as a
submodule, both of these directories may legitimately exist:

```text
repo/.repoworkflow/
repo/RepoWorkflow/.repoworkflow/
```

The first belongs to `repo` and is active while RWF operates on that consumer.
The second belongs to RepoWorkflow itself and is ignored for the enclosing
consumer operation.  It remains part of the RepoWorkflow checkout so that the
RepoWorkflow repository can use its own workflow when developed directly.

`RepoWorkflow/repo-workflow init` must resolve and initialize the enclosing
consumer rather than treating the executable's submodule as the consumer.
Subsequent lookup must use that resolved consumer root directly and must never
discover policy by recursively searching for `.repoworkflow` directories.

This separation prevents RepoWorkflow's self-hosting state from interfering
with repositories that consume it as a pinned submodule.

## `.ci/repoworkflow.json`

Recommended development shape:

```json
{
  "schema": 1,
  "versionCommand": ["python", "scripts/workflow-version.py"],
  "setVersionCommand": ["python", "scripts/workflow-version.py", "--set"],
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

The command is repository-owned. It must:

- exit zero only when the repository's version state is internally valid;
- print exactly one canonical development version to stdout;
- use the form `x.y.z-issue.<issue>.<iteration>`;
- leave the candidate worktree and history unchanged.

Lower-level distributed commands compare that value with `.ci/run-ci-request`.
The normal local `verify` path prepares that request binding before validation.

### `setVersionCommand`

`setVersionCommand` is the repository-owned mutation counterpart to
`versionCommand`. RepoWorkflow appends exactly one argument: the complete target
development version.

For example, this declaration:

```json
"setVersionCommand": ["python", "scripts/workflow-version.py", "--set"]
```

is invoked as:

```text
python scripts/workflow-version.py --set 1.2.3-issue.17.4
```

The setter may modify the consumer's version-bearing worktree files, but it must
not create commits, move `HEAD`, or mutate Git refs. RepoWorkflow re-runs
`versionCommand` afterward and requires the exact requested version.

The setter is optional for repositories that never need RepoWorkflow to advance
an already-consumed development iteration. It is required for the full
one-command workflow: if the authoritative remote already contains either
terminal tag for the current iteration, `verify` uses `setVersionCommand` to
advance to the next iteration automatically.

### `repository`

`integrationBranch` is the repository's normal integration line. The value must
also agree with `.ci/branch-policy.json`.

A development candidate may not run on `integrationBranch`. RepoWorkflow rejects
that state before authoritative development validation can begin. This prevents
an issue-qualified development identity from being accepted and tagged after it
has landed on the integration line. Stable publication is the separate path for
the integration branch and requires the repository version command to report a
plain stable `x.y.z` version.

`authoritativeRemote` is the Git remote used for authoritative branch/tag facts.
Failure to establish remote state is not interpreted as success.

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

1. reads the repository's development version;
2. checks authoritative terminal-tag state;
3. advances a consumed iteration through `setVersionCommand` when necessary;
4. refreshes `.ci/run-ci-request` after ordinary source commits when necessary;
5. commits only the bookkeeping/version changes it performed;
6. validates that prepared candidate through the normal guard;
7. runs required validation; and
8. automatically creates the PASS or FAIL terminal tag.

INCOMPLETE produces no terminal tag. `--push` pushes generated bookkeeping or
artifact commits and the terminal tag to `authoritativeRemote`. Candidate
preparation is rolled back if the setter, bookkeeping commit, or guard fails.

## `rwf config`

RepoWorkflow provides a state-aware configuration interface so repositories do
not require hand-editing JSON for ordinary policy/capability changes:

```text
rwf config
rwf config get [KEY]
rwf config set KEY VALUE
rwf config unset KEY
rwf config --json
```

Bare `rwf config` shows the effective repository configuration and its source.
`get` reads one value, `set` validates and persists one value, and `unset`
removes a repository override only when the resulting configuration remains
valid.  Unknown keys and invalid values are rejected before files are changed.

Configuration remains checked-in repository policy.  The command is an
interface to the schema, not a private per-worker settings database.  Changes
made by `rwf config` therefore remain ordinary reviewable repository changes.

Repository policy includes a pull-request mode:

```text
repository.pullRequests = required | allowed | disabled
```

- `required`: RWF must use the pull-request path at the applicable integration
  boundary and must not offer a direct alternative;
- `allowed`: a pull request is available but not intrinsically required by
  RWF policy;
- `disabled`: RWF does not offer/create a pull request for that boundary.

Repository validation capabilities may also declare relevant platform and
hardware facts.  Hardware configuration follows the same data-minimization
rule as validation evidence: declare capabilities needed to select or interpret
tests (for example a GPU/API or CPU feature), never machine identifiers or a
general inventory.

Secrets, credentials, tokens, hostnames, serial numbers, MAC/network addresses,
device IDs, and account identifiers are not valid RWF repository
configuration.

## `rwf pull-request`

`rwf pull-request` creates or reconciles the pull request appropriate to the
current workflow state:

```text
rwf pull-request
rwf pull-request --json
```

RWF derives the head branch, base branch, issue/integration identity, title,
body, and required workflow metadata from authoritative workflow state.  The
caller must not have to reconstruct those facts manually.

The command is idempotent: if the matching open pull request already exists,
RWF reports/reconciles that PR rather than creating a duplicate.  A conflicting
PR or ambiguous remote state is a STOP.

`what-next` and shell completion expose `pull-request` only when the current
state and `repository.pullRequests` policy permit it.  In `required` mode,
workflow transitions that would bypass the required PR are blocked.  In
`disabled` mode, `rwf pull-request` is rejected with the policy reason.

Creating a PR is not evidence that validation passed, that the base remains
current, that acceptance is complete, or that merge is authorized.  Those
remain independent workflow gates.

## Change classification

Repositories may define cheap, deterministic change classes in
`.repoworkflow/change-classes.json`.  Classification is based on the actual
changed-file set; commit messages are not authoritative.

```json
{
  "schema": 1,
  "classes": {
    "docs": {
      "paths": [
        "**/*.md",
        "docs/**",
        "VERSION"
      ],
      "validation": "fast"
    }
  }
}
```

Every changed path must match at least one path pattern in a class before that
class applies.  A single unmatched path falls back to `full` validation.  An
empty diff also falls back to `full`.  This makes a documentation change such
as `DESIGN.md` plus the required `VERSION` update eligible for cheap
validation without trusting a `docs:` commit-message assertion.

`rwf classify --base <commit> [--head <commit>]` reports the class, validation
level, and exact changed paths as JSON.  The same classifier is usable locally,
by GitHub Actions, or by another CI adapter.

RepoWorkflow's self-CI uses the `docs` class to keep its normal authoritative
validation but skip the cross-platform argv-limit probes, which do not provide
additional evidence for documentation-only changes.  Changes to source, tests,
workflow code, or any other unmatched path continue to receive full validation.

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
