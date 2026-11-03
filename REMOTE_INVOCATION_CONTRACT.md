# Generic remote RWF invocation — accepted design contract

**Status:** specification for #660, consolidated under #785. **Not yet
implemented.** This document describes the planned `.ci/rwf` mechanism;
[CI_INVOCATION_CONTRACT.md](CI_INVOCATION_CONTRACT.md) continues to govern
the implemented `.ci/run` mechanism. No protected cutover is authorized.

## Scope and precedence

This document is the single current design contract for #660. Its numeric
retry marker, CMD branch identity, centralized invocation wrapper, and
CMD-scoped result file **supersede earlier proposals** for a trailing Git
SHA, use of the issue branch as the request branch, implicit execution by a
second dispatcher, auto-deletion of CMD branches, and
`.repoworkflow/error` as the result destination.

The public grammar remains controlled by [COMMAND_GRAMMAR.md](COMMAND_GRAMMAR.md)
and [PUBLIC_WORKFLOW.md](PUBLIC_WORKFLOW.md). This contract specifies a
planned extension, not presently available command behavior.

AI phase skills #783 and security certification #784 are deferred; neither
is a prerequisite for #660. This exclusion does not waive current workflow
state invariants, request identity checks, or existing authorization rules.

## 1. One command implementation

The invocation `rwf test RED --remote` submits a remote request instead of
running that stage locally. The unnumbered `--remote` is the user-facing
request option. The hosted form `rwf test RED --remote 0` uses an **internal
numbered retry marker** and runs the existing local command implementation
inside one centralized invocation wrapper.

Every command follows its existing grammar and legal state transitions;
a remote mode never adds an alternate business-command dispatcher, duplicated
state machine, or remote-specific conditional inside individual handlers.
`rwf test results [--remote]` remains a read-only result lookup and does
not submit hosted work. `--poll` is client-side and is never recorded in
the hosted request.

The command's output and actual return code are captured by the wrapper,
which publishes the result through the existing Git/process interfaces.

## 2. CMD request identity and transport

For source branch `<source-branch>`, allocate a monotonically increasing
command number `N` under concurrency-safe Git publication and use branch
`CMD-<N>-<source-branch>`. Each *new* request branches from the **exact
current source branch tip**. Only the request branch receives transport
commits. The original source branch must not be changed simply to request
hosted execution. A new command or changed source revision gets a new CMD
identity.

The committed request file is `.ci/rwf`, a UTF-8 plain-text **argument
file**, not an executable script. It contains the arguments following the
normal `rwf` program name. For example:

```text
test RED --remote 0
```

The first submission uses retry count `0`. A permitted retry changes the
suffix to `1`, `2`, etc. on the **same CMD branch**, with a fresh
marker-only commit. Request/retry commits may change **only** `.ci/rwf`;
hosted result-publication commits are a separate permitted kind of commit
on the CMD branch.

**Argument representation:** The producer must preserve the user's
argument-vector tokens (excluding client-only `--poll`) and produce a
reversibly encoded plain-text argument sequence. The consumer decodes into
argv tokens and directly invokes the existing Python RWF entry point with
those tokens, never passing raw file text to a shell, `eval`, or a
provider-specific command interpreter. The implementation must define a
single writer/reader encoding and prove round-trip equality for whitespace,
quotes, backslashes, Unicode, and empty arguments before supporting those
inputs. Unspecified quoting or platform-dependent shell expansion is not
part of the accepted contract; no new command grammar is created here.

## 3. Central wrapper and execution boundary

A single CLI-boundary wrapper, before any normal command handler, owns:

1. Detecting the internal `--remote <retry-count>` suffix without
   exposing it as a public switch. The suffix is only legal for a valid
   authenticated CMD request, and is not offered by help or completion.
2. Asserting a `CMD-<N>-<source-branch>` request context, matching
   request metadata, original source tip and request/retry commit lineage.
   Missing, malformed, negative, mismatched or superseded markers are
   rejected before command execution.
3. Distinguishing request-only `.ci/rwf` commits from allowed hosted
   result-publication commits. A result file is forbidden on an ordinary
   source branch.
4. Establishing the original source execution context without permitting
   the internal marker to resubmit a hosted request.
5. Executing **exactly the same existing local command implementation**,
   capturing return code, stdout and stderr, and handing the outcome to
   CMD-scoped result publication.

No command handler performs its own CMD-branch assertion. Hosted CI is a
small provider bootstrap: event/path filter, checkout with pinned RWF,
Python runtime, and normal CLI invocation in **one worker/job**. GitHub
Actions is the first provider, not part of the core command semantics.

## 4. Result and readback contract

After a completed attempt, publish `.repoworkflow/result` on the CMD
branch **only**, with UTF-8 contents:

```text
<decimal exit code>
<captured stdout/stderr and diagnostics, if any>
```

The first line is the numeric command result, not a newly invented
success/failure category. Publication and readback must bind the result to
the current request revision and retry attempt; an earlier result does not
complete a newer retry. Preserve actual Unicode and nonzero outcomes and
handle publication conflicts without publishing an apparent success.
Keep CMD branches available for later readback, including unpolled clients.
Do not duplicate existing RWF test-result or lifecycle evidence stores.

Submitting a new valid request without polling reports CMD number and full
branch and exits `0`; invalid submission exits `1`. These are **request
submission outcomes**, not the remotely executed command's exit code.

## 5. Provider status, polling, and retries

Extend the existing **`repo-info`** adapter (not a new direct
GitHub/gh API in core RWF) with a normalized CI invocation status keyed by
CMD branch, request revision and attempt. Its semantic statuses include
queued, running, completed, not-observed, and unknown/error.
`not-observed` alone is **not** proof that a run cannot start later.

Planned client interface:

- `rwf remote-status [CMD#] [--poll [N0 [N1 ...]]]` is read-only.
  Omitted CMD# refers to the most recent command; negative indices use
  Python-style selection. Every response identifies resolved CMD# and branch.
- Without polling, return the terminal outcome if available, or an explicit
  **PENDING** status with a distinct reserved nonzero CLI code while work
  remains unfinished.
- `--poll` defaults to 15 seconds between checks. Supplied intervals
  are used in order and the final interval repeats. Polling never
  resubmits a request and `--poll` is not forwarded into `.ci/rwf`.
- A submitted `--remote --poll` request waits and returns the completed
  remote command's actual exit code and output.

Repeated submission of identical normalized command argv against the same
source revision reuses the existing CMD request, including its completed
result. Under 15 seconds since latest submission it does not retry.
At/after 15 seconds it performs a provider-status **check**, not an automatic
retry. Do not resubmit queued/running/unknown work. A retry requires positive
provider/lineage evidence that the previous attempt will not execute and
suppression of superseded attempts; otherwise report pending or unknown.

### Pending exit-code allocation

The current public dispatch in `repo_workflow/public_cli.py` uses
`0` for ordinary handled success and `2` for grammar/diagnostic
failures; the existing test and provider handlers supply additional command
results. The `rwf` shell launcher has its own `127` Python-not-found
error. **No globally collision-free pending code is yet established.**
Before implementing `remote-status`, #790 must audit all public and
forwarded exit paths, choose/document a reserved nonzero code and test its
status-output distinction from a completed command that returns that
same numeric value. The CLI must never report PENDING as success.
Do not invent a numeric constant merely because it is unused in a few
handlers.

## 6. Help, completion, and compatibility

Normal public command prefixes, `--help` and Bash completion derive from
one authoritative grammar. First Tab completes; second Tab uses the same
descriptions as `--help`. Do not publish the internal retry count or
numbered `--remote` suffix in ordinary help/completion, or add a generic
public `--remote` to commands where it was not already declared.
The remote transport of other authorized commands is a wrapper concern,
not a reason to rewrite public command grammar or handlers.

The **current implemented** CLI in
`repo_workflow/public_commands.py` declares public `--remote` only
for the `test` stages and read-only `test results`; #660 must
explicitly extend the user-facing grammar for new permitted remote
commands through the same grammar source. No code in #785 implements
that planned extension. Do not claim commands such as `rwf init --remote`
already work.

`.ci/run` and its on-demand GitHub workflow remain operational with
their existing event filter. The new CMD-only `.ci/rwf` trigger must be
distinct. No merge, protected-branch activation, migration, or replacement
is authorized merely by this design contract.

## 7. Required implementation and verification ownership

- #786 owns the central invocation wrapper and CMD assertions.
- #787 owns request allocation, submission, idempotent identity and Git
  lineage.
- #792 owns the normalized provider-status adapter.
- #788 owns the hosted bootstrap invoking the **normal** RWF CLI.
- #789 owns CMD-only results publication/readback.
- #790 owns client status/polling and safe retry policy.
- #791 owns assembled exact-source native Linux/macOS/Windows and genuine
  hosted end-to-end verification using Disposable-001.

Coordination, file ownership discussions, and communication are **not**
dependency edges; consult [WORK_GRAPH_SCHEDULING.md](WORK_GRAPH_SCHEDULING.md)
for actual direct prerequisites. Security #784 and phase skills #783
remain deferred.

## Design and acceptance expectations

Reuse the existing command handlers, CLI grammar, Git abstractions and
provider adapter interfaces. Build and verify the complete working model
before profiling or optimizing; do not introduce speculative caches,
platform branches, or extra dispatchers. See
[DESIGN_PRINCIPLES.md](DESIGN_PRINCIPLES.md).

Run parser/help/completion invariants, invalid CMD context, exact
request ancestry, retries, output/result failure paths and native three-OS
acceptance on the **implemented** exact revision. Provider fixture tests
are not a substitute for live hosted CI acceptance.
