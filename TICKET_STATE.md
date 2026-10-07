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
6. commit the synchronized ticket-state update with the ticket-creation work;
7. read the committed state back and verify every new ticket's exact title and
   complete direct dependency set;
8. leave the records ready for explicit `to-tickets` synchronization.

Ticket creation is not complete when dependency information exists only in
issue prose or conversation context.  An agent must not report ticket creation
complete until the canonical synchronized state has been committed and read
back successfully.

Human-authored tickets normally originate with provider dependencies and are
acquired through `from-tickets` or first-use provider acquisition.

When a newly created ticket is part of a larger decomposed task, update the
canonical dependency graph in the same ticket-creation work so traversal can
recover the route back to the larger outcome.  Do not leave the relationship
only in issue prose, chat history, or a human memory of why the ticket exists.
Use only real direct executable dependencies: connect leaves through their
actual prerequisites and convergence/certification work, and do not invent a
dependency merely to encode container membership.  A newly created ticket must
not be left absent from `.repoworkflow/tickets.csv` while dependent work
continues.

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

The repository declares the `rwf-tickets` merge attribute. Repository
initialization must register the matching driver command so Git invokes
`scripts/merge-ticket-state.py` with the merge-base, current, and other
temporary paths. The merge implementation itself is repository-portable; the
Git configuration is clone-local because Git does not load merge-driver
commands from committed attributes.

## 9. Git merge-driver activation

The repository marks the synchronized file with:

```text
/.repoworkflow/tickets.csv merge=rwf-tickets
```

Normal `rwf` use configures the repository-local Git driver named
`rwf-tickets` to invoke the current RepoWorkflow engine's
`scripts/merge-ticket-state.py` with Git's base/ours/theirs files.

The driver command is clone-local configuration. It is not committed with a
machine-specific Python path.

A repository using the synchronized ticket file must configure the driver
before relying on automatic semantic merges. RepoWorkflow does this during
normal public command execution; repository initialization should establish the
same configuration before handing the repository to users/agents.

## 10. Verification

TEST_ADEQUACY.md applies. Verification must independently cover parsing,
canonical serialization, migration, restart/readback, synchronization
directions, compare-only behaviour, selective replacement, title mismatch,
provider failure, multi-ticket atomicity/rollback, and semantic merge cases.
