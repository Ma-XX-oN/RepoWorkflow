# Synchronized Ticket State

Status: authoritative contract for durable ticket identity and dependency state.

## 1. Purpose

RepoWorkflow keeps one durable repository copy of the ticket facts needed for
offline workflow operations and fast repeated dependency traversal.

The synchronized record for each ticket contains exactly:

- positive ticket number;
- exact provider title;
- exact direct dependency set.

The canonical file is:

```text
.repoworkflow/tickets.csv
```

with columns:

```text
issue,title,dependencies
```

Rows are ordered by issue number. Dependencies are sorted positive issue
numbers separated by semicolons. An empty dependency field means the ticket is
known to have no direct dependencies.

## 2. Authority

Title authority is unconditional:

```text
ticket server -> title
```

A local title is a synchronized copy. A mismatch must never be pushed as an
implicit rename.

Dependency authority is selected explicitly by synchronization direction:

```text
from-tickets: ticket server -> repository
to-tickets:   repository    -> ticket server
```

A `to-tickets` operation requires the exact provider title to match the
synchronized local title before changing dependencies.

Every provider synchronization acquires title and dependencies together.

## 3. Public synchronization

One or more explicit issues may be synchronized:

```text
rwf issue <ISSUE...> dependency from-tickets
rwf issue <ISSUE...> dependency to-tickets
```

Comparison is read-only:

```text
--compare
```

`from-tickets` supports explicit conflict choices:

```text
--replace
--replace-title
--replace-dependencies
```

`--replace` accepts provider title and dependencies.
`--replace-title` accepts the provider title while preserving conflicting
local dependencies.
`--replace-dependencies` accepts provider dependencies; provider title
remains authoritative.

`to-tickets --replace` replaces conflicting provider dependencies only.
There is no title-push operation in dependency synchronization.

## 4. Ticket title taxonomy

Ticket creators use these descriptive prefixes when they improve navigation:

- `Initiative:` for broad programme-level containers;
- `Epic:` for large outcome containers;
- `Feature:` for coherent capabilities;
- no prefix for ordinary executable implementation or certification tasks.

Prefixes are presentation only. RepoWorkflow does not infer dependencies,
readiness, branch topology, ownership, or execution semantics from a title.

## 5. Ticket creation

When RWF or an agent creates/decomposes tickets:

1. create the provider tickets;
2. record every new ticket number and exact returned provider title locally;
3. record every known direct dependency;
4. record an explicit empty dependency set when no direct dependency is known;
5. validate the resulting dependency graph;
6. leave the records ready for explicit `to-tickets` synchronization.

Ticket creation is not complete when dependency information exists only in
issue prose or conversation context.

Human-authored tickets normally originate with provider dependencies and are
acquired through `from-tickets` or first-use provider acquisition.

## 6. Dependency invariants

Only direct dependencies are stored.

The graph must contain no:

- self dependency;
- duplicate dependency;
- unknown dependency target;
- dependency cycle.

Transitive prerequisites are obtained by traversal. A redundant transitive
edge is not stored unless it represents an independently required direct
interface.

## 7. Branch-parent separation

Branch parent identity is not ticket state.

A work branch records its parent in Git history using:

```text
RWF-Branch: <work-branch>
RWF-Parent: <parent-branch>
```

Git branch identity/history is the sole parent authority. Ticket dependency
topology never creates or stores a branch parent.

## 8. Semantic merge

The synchronized CSV is merged by ticket number, not line position.

Dependency changes use normal three-way semantics:

- one-side-only change: accept;
- identical changes: accept;
- divergent changes on both sides: conflict.

Title conflicts are resolved from the authoritative ticket server. If the
server cannot be consulted when a title conflict requires resolution, the
merge fails rather than guessing.

The merged file contains at most one canonical row per ticket.

## 9. Verification

TEST_ADEQUACY.md applies. Verification must independently cover parsing,
canonical serialization, migration, restart/readback, synchronization
directions, compare-only behaviour, selective replacement, title mismatch,
provider failure, multi-ticket atomicity/rollback, and semantic merge cases.
