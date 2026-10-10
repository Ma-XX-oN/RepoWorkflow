# GitHub repo-ci artifact and result transport (#93)

The portable contract is REPO_CI_CONTRACT.md (#65). This adapter segment owns
GitHub Actions artifact **transport only**. It has no authority to set
PASS/FAIL/INCOMPLETE, merge, tag, or move a lifecycle state. Core RWF evaluates
retrieved observations and applies the portable contract.

## Boundary

`repo_workflow.github_result_transport` stages an immutable directory bundle:

- `manifest.json`: version 1, invocation ID, exact candidate repository,
  commit and base identities, and declared artifact names, lengths and SHA-256.
- One binary file per declared artifact name, with exact retained bytes.

`publish_bundle(request, records, directory)` accepts a portable version-1
publish request and writes a **new** bundle; an occupied destination is a
conflict. `fetch_bundle(directory, invocation, candidate, declared)` performs
a read-only, repeatable check of every required file and returns the bytes.
Neither operation interprets validation results.

`python -m repo_workflow.github_transport_cli` exposes the same operations
for separate runner processes. Each invocation requires an explicit request
JSON, source directory, and destination directory. The request operation must
match the CLI command. An unsuccessful request exits nonzero (2); the caller
must record missing or invalid transport as INCOMPLETE, never PASS or FAIL.

## GitHub Actions binding

An upload job stages a bundle, then uploads its entire directory with
`actions/upload-artifact@v4` and `if-no-files-found: error`. A later job
in the **same workflow run** downloads the named artifact using
`actions/download-artifact@v4` and checks the bundle with the exact original
invocation, repository, candidate commit and base commit supplied by core.

The GitHub Actions run and artifact locator are externally verified by the
calling workflow. The directory digest is an integrity check, not a signature;
the transport alone cannot authenticate the producing workflow or certify
a result. The validator must also check all required stage identities and
observations against the core-owned requirements before classification.

The isolated acceptance workflow
`.github/workflows/repo-ci-transport-acceptance.yml` demonstrates a real
two-job upload/download exchange and verifies that the payload is unchanged.
The existing GitHub machine entrypoints are migrated by #67 after #91-#94;
this issue does not alter their deployed lifecycle behaviour.

## Acceptance and failure behaviour

- Zero, one and multiple artifact declarations retain exact bytes.
- Missing, corrupt, undeclared, duplicate, or modified content fails closed.
- Changed candidate repository, commit, base, or invocation fails closed.
- Duplicate or conflicting publication never overwrites a previous bundle.
- Reserved `manifest.json` and path traversal names are forbidden.
- Failed real validation stays a *data observation*, not adapter-certified FAIL.
- Retrieving complete evidence is not proof that all required test stages ran.
- Retries are separately identified by invocation; fetch is read-only.
- Provider-specific execution/provenance remains inside the GitHub adapter.

Tests: `tests.test_github_result_transport` and
`tests.test_github_transport_cli`, registered under their issue-93 groups
in `.ci/tests.json`. The two-job GitHub Actions workflow is a separate hosted
provider acceptance gate. Full repo-ci compatibility migration is owned by #67.
