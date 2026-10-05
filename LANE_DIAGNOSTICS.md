# Lane Invocation Diagnostics

Status: authoritative contract for progress and performance diagnostics emitted
by lane commands.

## 1. Purpose

Lane commands may perform slow provider work.  Users must be able to distinguish
provider/network delay from local relationship, decomposition, or rendering
work without changing command semantics.

Diagnostics are observability data only.  They are never dependency, lifecycle,
selection, or provider authority.

## 2. Progress output

Provider activity emits concise progress on stderr.

Examples:

```text
Refreshing dependencies: #203
Refreshing metadata: 1/3 (#201)
```

When a total is known, progress includes completed/total counts.  Dynamically
discovered dependency traversal may report the issue currently being read
without claiming a final total that is not yet known.

Purely local successful lane reads are quiet by default.

stdout remains reserved for the command result or explicit `--debug`
diagnostic projection.

## 3. Invocation records

Each valid lane invocation creates one clone-local record under the Git common
directory:

```text
<git-common-dir>/repoworkflow/diagnostics/lanes/
  lane-invocation--<uuid>.json
```

The UUID is freshly generated for each invocation, so independent workers never
append to or update one shared diagnostics file.

Each record contains:

- schema version and invocation UUID;
- start timestamp;
- repository HEAD when available;
- literal lane command words;
- total elapsed time;
- provider call counts by family;
- provider elapsed time by family;
- cache hits/misses by family;
- local phase timings;
- canonical direct semantic edges observed by the command;
- routed-edge diagnostics when supplied by the #345 router;
- success/failure and the semantic error text when the command failed.

Provider payloads, authentication data, tokens, and environment secrets are
never recorded.

## 4. Debug projection

`rwf lanes view --debug` renders the normal graph, followed by a concise
projection of the in-memory diagnostics for that invocation.

It includes:

- provider request count;
- relationship/metadata cache hits and misses;
- provider and local phase timings;
- canonical direct edges;
- routed-edge identities once #345 supplies them.

Debug output does not cause a refresh.  Provider access still follows
LANE_CACHE_REFRESH.md.

## 5. Failure isolation

Diagnostic persistence is best-effort.

A diagnostics write failure:

- does not roll back or corrupt workflow state;
- does not convert a successful semantic command into failure;
- does not convert a semantic failure into success;
- emits a warning on stderr.

Provider/workflow errors remain primary.

## 6. Verification

Tests must independently prove:

- no provider calls -> no progress output;
- one/many provider calls -> correct stderr progress and counts;
- provider failure still records diagnostics;
- stdout/stderr separation;
- success/failure records have correct semantic status;
- concurrent invocations create distinct records;
- timing values are non-negative and internally attributable;
- diagnostic records contain no provider payload/secret values;
- write failure is non-fatal;
- assembled `lanes view --debug` reports cache/provider/direct-edge facts
  matching the canonical state used by the command.

All applicable TEST_ADEQUACY.md requirements apply.


## Failure privacy

Durable diagnostics record the exception class for a failed invocation, not raw
exception text.  The normal command stderr remains the actionable user-facing
error channel.  This prevents provider stderr, payload fragments, tokens, or
other secrets from being copied into diagnostic records.
