# Validation Result Diagnostics

RepoWorkflow preserves the narrow authoritative result model:

- `PASS`: every required result was established and passed;
- `FAIL`: every required result was established and at least one genuinely failed;
- `INCOMPLETE`: at least one required result could not be established.

## Local capability checks

Before a local validation command runs, RepoWorkflow checks the declared platform and any versioned toolchain capabilities it understands.

Supported versioned capability forms are:

- `node-<version>`;
- `python-<version>`;
- `dotnet-<version>`.

The requested numeric components are exact prefixes of the detected runtime version. For example, `node-22` accepts a detected `22.x.y`, while `python-3.13` requires Python `3.13.x`. A missing tool, an unparseable version, or a version mismatch makes that environment `INCOMPLETE` and the validation command is not run.

Other capability labels remain declarative requirements. RepoWorkflow does not claim to have verified a capability it does not understand.

## Actionable validation output

RepoWorkflow records the validation command return code, captured stdout, and captured stderr for every executed environment.

A validation command may return exit code `2` to state that the required result could not be established. RepoWorkflow records that as `INCOMPLETE` with an explicit reason. Any other nonzero return code is a genuine `FAIL`, also with an explicit return-code reason.

Before temporary result storage is removed, final local reporting prints the environment reason and any captured stdout/stderr for both `INCOMPLETE` and `FAIL`. A known reason must not be reduced to only an aggregate environment status.

Capability or platform failures are `INCOMPLETE` and are reported with their specific reason, such as a missing tool or detected version mismatch; because the validation command is not run in that case, there is no command output to print.

`INCOMPLETE` never creates a terminal result tag. Genuine `FAIL` continues to create `v<version>-CI-FAIL` when terminal tagging is enabled; exposing diagnostics does not change result or tagging semantics.
