# RepoWorkflow Configuration

RepoWorkflow schema 1 keeps repository-specific facts in the consumer while the
shared engine owns lifecycle semantics and invariants.

## `.ci/repoworkflow.json`

Required shape:

```json
{
  "schema": 1,
  "versionCommand": ["python", "scripts/workflow-version.py"],
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

RepoWorkflow compares that value with `.ci/run-ci-request`.

### `repository`

`integrationBranch` is the repository's normal integration line. The value must
also agree with `.ci/branch-policy.json`.

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
silently choosing one.  When no Python capability is declared, GitHub uses
Python 3.13 for the RepoWorkflow engine and repository command.  Other
capability labels remain declarative requirements of the selected runner and
repository validation command; the shared adapter does not pretend to provision
capabilities it does not understand.

Validation exit codes are:

- `0`: PASS;
- `1` or another non-zero code except `2`: genuine FAIL;
- `2`: INCOMPLETE because the required result could not be established.

A validation command must not modify the candidate worktree, commit history,
symbolic `HEAD` target, or local Git refs.  RepoWorkflow records the violation,
restores the known-clean candidate state, and continues independent validation
where possible.

### `artifacts`

Repositories with committed generated artifacts may declare them.  The artifact
mechanism is intentionally only for committed generated artifacts; a
`committed: false` declaration is rejected.  Each artifact has:

- unique `id`;
- `generatorCommand`;
- a different, independent `verifierCommand`;
- non-empty `outputs` allow-list;
- optional `platform` and `capabilities` declarations.

Numeric Node/Python artifact capabilities use the same GitHub projection rules
as validation environments so the preparation job runs the generator and
verifier under the declared toolchains.

Generation may change only declared outputs.  Verification must be read-only.
RepoWorkflow rejects generator/verifier worktree, history, symbolic-HEAD, or
local-ref mutation outside the authorized generated-output commit.  A failed or
incomplete artifact gate is recorded with the same candidate identity used by
the validation matrix and participates in terminal result aggregation.

The full local `verify` path materializes and commits successful declared
artifact changes using the same allow-list safeguards before validating the new
candidate.  Failed/incomplete artifact-script side effects are rolled back to
the previously established clean candidate before independent validation
continues.

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

## `.ci/branch-policy.json`

The branch policy declares intended ancestry. Schema 1 provides:

- `integrationBranch`;
- exact `branches` rules;
- optional ordered `patterns` rules;
- per-rule `parent`;
- `allowedDependencies`;
- `umbrella`;
- `integrationTarget`.

RepoWorkflow refreshes authoritative remote ancestry before evaluating the
branch. Unmatched non-integration branches are rejected.

## `.ci/run-ci-request`

This file contains exactly the requested development version. It is a universal
candidate guard. GitHub additionally treats a modification of this file (or an
explicit manual dispatch) as the request to spend remote CI resources.

After the request commit, only declared committed generated-artifact paths may
change before the tested candidate; source changes require a new issue
iteration/request.

## GitHub adapter

A consumer's `.github/workflows/ci.yml` must match
`RepoWorkflow/templates/github/ci.yml` byte-for-byte. Product-specific commands
or policy do not belong in that YAML.
