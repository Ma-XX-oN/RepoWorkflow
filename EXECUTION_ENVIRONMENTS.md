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
3. **Hosted execution required or useful?** Use an authorised GitHub Actions
   workflow as a temporary **workbench** to run an isolated measurement,
   install packages, exercise native OS behavior or obtain actual runner logs.
4. **Other execution provider?** Prefer the task's required provider if it
   has authority or platform coverage that a GitHub runner lacks.
5. **No appropriate environment?** Report precisely what was attempted,
   why it failed, and which acceptance criteria remain incomplete.

An executable isolated experiment is not the same as the repository's full
test suite or live production-provider certification.

## GitHub Actions as a diagnostic workbench

Use when the local runtime lacks a package, toolchain, network access,
native operating system, or other test prerequisite.

- First inspect existing CI workflows and recent runs; reuse an existing
  approved mechanism when it fits.
- For an isolated experiment, use a dedicated short-lived branch and a
  narrowly scoped workflow. Do not change production code or protected
  `main` merely to probe a tool.
- Pin the **source commit** independently from the workflow-trigger commit.
  Explicitly install and report dependency versions and test environment.
- Grant the minimum workflow permissions (`contents: read` where enough),
  limit runtime and workload, and avoid secrets or provider mutations unless
  expressly authorised.
- Emit concise, machine-readable evidence in logs: revision, inputs,
  tool versions, measurements, expected outcomes and digest where useful.
- Read the final job **conclusion** and logs. A queued or started job is
  not passing evidence.
- Record the workflow run and job URLs, exact SHA, results and limitations
  in the owning issue or permanent documentation when relevant.
- Temporary workbench success proves only the isolated requirement tested.
  Follow [test adequacy](TEST_ADEQUACY.md) for exact-revision native,
  integration and genuine provider acceptance.

## Recorded example: token measurement

The local Python environment could not resolve the package index, so a
hosted Ubuntu GitHub Actions job installed `tiktoken==0.12.0`. It measured
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
