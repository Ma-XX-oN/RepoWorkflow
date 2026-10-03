# Local Workspace Model

Status: authoritative semantic contract for repository-local parallel RWF
workspaces.

This document defines the workspace abstraction independently of Git worktree
mechanics, shell presentation, GitHub, or WorkStack.

A workspace is clone-local operational state that lets one worker safely own
and resume one issue context while other workers operate in parallel.

## 1. Scope and authority

A workspace records local execution context only.

Authoritative shared facts remain elsewhere, including:

- issue identity and open/closed state;
- child ownership and shared umbrella attachments;
- direct leaf and umbrella dependencies;
- durable issue lifecycle/history;
- validation evidence;
- integration and release evidence.

Workspace records may reference those facts, but never replace them.

The workspace layer owns:

- local workspace identity;
- issue association;
- local lifecycle state;
- claim revision and worker/session identity;
- local resume metadata;
- references to the branch/worktree used for the workspace.

## 2. Workspace identity

Each workspace has one stable local identifier.

The identifier:

- is unique within one RWF-managed clone;
- remains stable across chat/session rollover;
- maps to exactly one repository issue;
- is not derived from a transient process ID or shell session;
- does not become a repository-wide authoritative issue identity.

A suggested human-readable form is:

```text
RWF-<issue-number>
```

Implementations may use a collision suffix when more than one local workspace
for the same issue is explicitly supported in the future.  The initial model
permits at most one active local workspace per issue per clone.

## 3. Workspace lifecycle

The semantic lifecycle is:

```text
AVAILABLE
   |
   | claim
   v
CLAIMED
   |
   | begin/resume
   v
PROCESSING
   |        \
   |         \ dependency/external condition
   |          v
   |        BLOCKED
   |          |
   |          | condition clears
   |          v
   |       PROCESSING
   |
   +--> COMPLETE
   |
   +--> ABORTED
```

### 3.1 AVAILABLE

The workspace exists locally but has no current worker claim.

A worker may claim it only with the current claim revision.

### 3.2 CLAIMED

Exactly one worker owns the local execution slot.

Claimed does not mean the durable issue has started or that a branch/worktree
mutation has completed.  Those are separate transitions.

### 3.3 PROCESSING

The claimed worker has entered the workspace and may perform issue work.

The local workspace must retain enough information to resume after process,
shell, chat, or agent-session loss.

### 3.4 BLOCKED

The workspace remains owned but cannot currently advance because of an explicit
condition.

BLOCKED is not inferred from inactivity.

A blocked record must include an actionable blocker description or reference.

### 3.5 COMPLETE

Local work for the workspace has reached its required terminal condition and
all required durable workflow facts have already been recorded elsewhere.

COMPLETE does not itself imply branch deletion, worktree deletion, merge, or
release.

### 3.6 ABORTED

The local workspace was intentionally abandoned.

Abort must preserve any already-durable workflow history and must not erase
uncommitted or otherwise non-durable work.

## 4. Claim contract

Claims use compare-and-swap semantics.

Each claim record contains at least:

```text
workspace_id
status
revision
worker_id
session_id
```

The claim revision is a non-negative integer.

A newly created unclaimed workspace may begin at revision 0.

Every successful claim-state mutation increments revision by exactly one.

A caller must supply the revision it observed.

For example:

```text
AVAILABLE rev 3
      |
      | claim(expected=3)
      v
CLAIMED rev 4
```

If another worker already changed the claim:

```text
caller observed rev 3
current revision is rev 4
=> reject as stale
```

No claim operation silently retries against the newer revision.

## 5. Worker and session identity

`worker_id` identifies the logical worker that owns the claim.

`session_id` identifies the current transient execution/chat/session when
available.

The worker identity may survive session rollover.

Changing only the session identity for the same worker is a claim mutation and
therefore increments the revision.

Neither worker nor session identity is a security credential.

## 6. Legal claim transitions

The initial claim-state transitions are:

```text
available -> claimed
claimed   -> available
claimed   -> blocked
blocked   -> claimed
claimed   -> closed
blocked   -> closed
available -> closed
```

The storage representation may use lower-case claim-state names while the
workspace lifecycle uses the semantic names above.

A transition is legal only when:

1. the expected revision equals the current revision;
2. the requested source state matches current state;
3. required worker identity checks pass;
4. any destructive cleanup preconditions have already passed.

Illegal transitions fail without changing the record.

## 7. Ownership rules

A claimed workspace belongs to one worker at a time.

Another worker may not:

- overwrite the claim;
- change the current session identity;
- mark the workspace complete or aborted;
- retire its worktree;
- clean up its local state;

unless an explicit recovery/takeover operation is defined and its preconditions
are satisfied.

The initial contract does not include forced takeover.

## 8. Resume and re-entry

A workspace resume record must provide enough local context to answer:

- which issue this workspace belongs to;
- which branch/worktree is associated with it;
- which claim revision is current;
- which worker owns it;
- what the last known local lifecycle state is;
- what exact next local action was recorded;
- which durable facts must be re-read before continuing.

Resume state is advisory local context.

On re-entry, authoritative durable state must be re-read before any mutation.
A stale resume record cannot override newer durable facts.

## 9. Workspace creation

Creating a workspace establishes only local operational identity unless a later
command explicitly performs canonical issue-start semantics.

Workspace creation must not by itself fabricate:

- durable issue-start history;
- validation evidence;
- dependency edges;
- branch-base semantics;
- integration authorization.

The command layer may later compose provisioning and issue start into one user
operation, but the semantic layers remain distinct.

## 10. Relationship to issue readiness

Workspace existence and issue readiness are separate facts.

A workspace may exist before an issue becomes ready if the command contract
explicitly permits provision-only behaviour.

Beginning issue work requires the readiness rule owned by the work graph:

- no unresolved direct leaf dependencies => ready;
- one or more unresolved direct leaf dependencies => blocked.

Umbrella membership, shared attachment, and branch base do not create readiness
edges by themselves.

## 11. Relationship to WorkStack

WorkStack may allocate cross-repository work to a repository-local RWF
workspace.

RWF remains authoritative for repository-local workspace semantics and Git
execution mechanics.

WorkStack does not become the authority for local branch/worktree state merely
because it requested allocation.

Likewise, RWF local workspace records do not replace WorkStack's durable
cross-repository lane state.

## 12. Failure atomicity

Each workspace mutation must have one of two observable outcomes:

- complete success with exactly one new valid state; or
- failure with the prior valid state preserved.

No operation may report success while only some of its workspace metadata was
updated.

If a later Git/backend operation fails after a local record was tentatively
created, the caller must either roll back the record or leave an explicit,
recoverable non-success state defined by the provisioning contract.

## 13. Cleanup and retirement

Closing a workspace is not permission to destroy local work.

Before retirement, the implementation must prove that required durable state
exists and that no protected local work would be lost.

At minimum, cleanup must refuse to remove a workspace when:

- its worktree has uncommitted changes;
- required recovery metadata exists only locally and has not been preserved;
- another worker owns the current claim;
- the workspace state does not permit retirement.

Retirement removes disposable local execution context only.

Durable issue/workflow history remains intact.

## 14. Storage boundary

The concrete path/layout is owned by the clone-local state layout contract.

The workspace semantic model requires only that:

- workspace records are clone-local;
- workspace namespaces cannot alias durable/shared state;
- writes are atomic;
- claim revisions are validated centrally;
- one clone cannot overwrite another clone's local state through repository
  commits.

## 15. Contract tests

Implementations must cover at least:

1. create one AVAILABLE workspace;
2. claim revision 0 successfully;
3. reject a second claim using stale revision 0;
4. release a claim with the current revision;
5. preserve worker identity across session rollover;
6. reject mutation by a non-owning worker;
7. move PROCESSING <-> BLOCKED without losing claim ownership;
8. refuse retirement when protected local work exists;
9. prove clone-local records do not enter committed shared state;
10. prove failed writes leave the prior valid state intact.

Production code should not weaken these semantics for command-line convenience.
