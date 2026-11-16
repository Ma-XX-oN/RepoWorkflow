# Execution Environments and Workbench Selection

**Purpose:** Choose the simplest authorised environment that can produce
the evidence required by the task. Local environment failure is a reason to
change tactics, not a reason to abandon independently executable verification.

This is an execution-selection procedure, **not** permission to bypass
repository security, protected branches, approvals, ownership or releases.

## Quick decision

1. **Local environment available and sufficient?** Run the exact test locally.
   Record interpreter, dependencies, platform and source SHA.
2. **Dependency missing or local network unreachable?** Check installed
   versions, package caches, virtual environments, mounted files and any
   approved alternate interpreter. Do not retry identical failures blindly.
3. **Hosted execution required or useful?** Use any authorised CI runner as a
   temporary **workbench** to install dependencies, reproduce a native failure,
   run isolated measurements or collect provider logs. Choose by capability,
   availability, cost and authority, not by provider brand.
4. **Provider-specific acceptance?** Use the provider and environment
   required by the task. A different CI service's isolated test cannot
   substitute for that provider's authenticated acceptance.
5. **No appropriate environment?** Report precisely what was attempted,
   why it failed, and which acceptance criteria remain incomplete.

An executable isolated experiment is not the same as the repository's full
test suite or live production-provider certification.

## Any authorised CI system as a diagnostic workbench

RepoWorkflow is CI-provider-neutral. GitHub Actions is one currently used
example, **not** a required host or a permanent architectural dependency.
Other CI services can provide the same isolated execution capability when
available and authorised. Use this procedure whenever the local runtime
lacks packages, network access, toolchains, native OS support or another
prerequisite.

- First inspect the repository's configured CI provider, existing workflows
  and recent runs; reuse an approved mechanism when it fits.
- For an isolated experiment, use a dedicated short-lived branch and a
  narrowly scoped workflow. Do not change production code or protected
  `main` merely to probe a tool.
- Pin the **source commit** independently from the workflow-trigger commit.
  Explicitly install and report dependency versions and test environment.
- Grant minimum provider-appropriate permissions (read-only source access
  where sufficient), limit runtime and workload, and avoid secrets or
  provider mutations unless expressly authorised.
- Emit concise, machine-readable evidence in logs: revision, inputs,
  tool versions, measurements, expected outcomes and digest where useful.
- Read the provider's terminal job **conclusion** and logs. A queued or
  started job is not passing evidence.
- Record the workflow run and job URLs, exact SHA, results and limitations
  in the owning issue or permanent documentation when relevant.
- Temporary workbench success proves only the isolated requirement tested.
  Follow [test adequacy](TEST_ADEQUACY.md) for exact-revision native,
  integration and genuine provider acceptance.

## CI invocation marker: current versus planned

The implemented GitHub on-demand workflow uses **`.ci/run`** as its sole
invocation marker for `issue-*` branch pushes. An ordinary source-only push
cannot trigger that workflow. Other independently configured workflows may
have different push triggers. `.ci/run-ci-request` is a distinct legacy
candidate-binding file and is not the on-demand trigger. A future migration intends to use **`.ci/rwf`**; that future name
is **not the current executable interface**. Do not change invocation paths
or claim the migration is active without an implemented, accepted contract.
The invocation marker and its syntax are conceptually independent of the CI
provider. CI services should adapt the provider-neutral invocation semantics
to their own trigger and runner capabilities.

For current marker semantics and implementation-status caveats, consult
[CI_INVOCATION_CONTRACT.md](CI_INVOCATION_CONTRACT.md). Workbench probes can
also use a provider's approved isolated mechanism instead of pretending to
be a normal RWF stage invocation. Keep them distinct in evidence and logs.

## Recorded example: token measurement

The local Python environment could not resolve the package index, so an
available hosted Ubuntu GitHub Actions job installed `tiktoken==0.12.0`. It measured
the first 800 Python lines of `tests/test_first_use_lanes.py` at pinned
revision `b7f39e33837bcbb9e22cd88bb63222d3149b416d` using
`o200k_base`: **6,456 tokens** and **24,837 UTF-8 bytes**.

[Actions run 41210454306](https://github.com/Ma-XX-oN/RepoWorkflow/actions/runs/41210454306)
completed successfully. See
[source-size rationale](SOURCE_SIZE_RATIONALE.md) for the sample digest,
exact interpretation, and its distinction from the 10,000-token
`functions.exec` output cap.

The original failed pip operation was a **local connectivity limitation**,
not proof that GitHub Actions or pip could not install `tiktoken`.

## Cross-topic links

- [Investigation method](BUG_INVESTIGATION.md): evidence-driven diagnosis.
- [Test strategy](TEST_STRATEGY.md): stage and platform selection.
- [CI invocation contract](CI_INVOCATION_CONTRACT.md): product CI semantics;
  experimental workbench runs do not replace authoritative stage gates.
- [Test adequacy](TEST_ADEQUACY.md): criteria for claiming verification.
- [Agent execution and handoff](AGENT-CMD-PROTOCOL.md): continuation,
  approvals, checkpoints and evidence boundaries.
