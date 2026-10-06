# Parent Branch Workflow

Status: authoritative branch-parent identity and recovery contract.

## 1. Single source of truth

Every RWF work branch has exactly one semantic parent branch.

The work branch is created from that parent and successful completion integrates
back into that same parent.

The parent is represented only by Git branch history. It is not stored in
ticket/dependency state.

Dependency topology never implies branch topology, and branch topology never
creates a dependency edge.

## 2. Parent identity marker

The first commit created specifically for an RWF work branch is an empty
structured identity commit.

Its first parent is the exact creation-parent tip. Its commit message contains:

```text
RWF-Branch: <canonical-work-branch-name>
RWF-Parent: <canonical-parent-branch-name>
```

Names are canonical branch names without ref prefixes.

The marker is permanent logical branch history. Pause checkpoints and later
work never modify or replace it.

## 3. Creation

For new work branch `W` from current branch `P`:

1. require a non-detached, unambiguous current branch `P`;
2. resolve the exact parent tip;
3. create and check out `W` from that tip;
4. create exactly one branch-identity commit naming `W` and `P`;
5. continue normal work from that commit.

No ticket relationship record is written for the parent.

## 4. Recovery

Given work branch `W`:

1. walk its first-parent history;
2. locate structurally valid identity commits whose `RWF-Branch` exactly
   equals `W`;
3. require exactly one matching marker;
4. read its `RWF-Parent` value `P`;
5. resolve local and fetched remote-tracking refs for that exact branch name;
6. require every accepted representation of `P` to contain the identity
   commit's first parent in its ancestry.

Missing, malformed, duplicate, conflicting, or topologically invalid evidence
fails closed.

Recovery performs no network operation.

## 5. Required cases

The same rules cover:

- `main -> issue`;
- `main -> lane -> issue`;
- siblings;
- nested work branches;
- parent advancement;
- unrelated equal-tip refs;
- fetched clones;
- deleted local parent refs with a valid fetched remote representation.

Inherited identity markers for ancestor work branches are ignored because their
`RWF-Branch` value does not equal the current work branch.

## 6. Invariants

- A work branch has exactly one semantic parent.
- Creation parent and completion target are the same fact.
- Parent identity is recorded once in Git history.
- No independently mutable parent/integration-target field exists in
  synchronized ticket state.
- Dependency changes cannot change branch parent.
- Siblings and descendants cannot replace another branch's parent.
- Recovery never depends on Git ref enumeration order.
- Ambiguity fails closed.
- Normal push/fetch preserves parent evidence.

## 7. Verification

Implementations test at least:

1. main -> issue;
2. main -> lane -> issue;
3. siblings;
4. parent advancement;
5. equal-tip unrelated refs;
6. nested branches;
7. fetched clone recovery;
8. deleted local parent with fetched remote parent;
9. missing parent representation;
10. duplicate/conflicting/malformed matching markers;
11. rewritten parent history;
12. ref enumeration order independence;
13. dependency changes leaving parent recovery unchanged.

TEST_ADEQUACY.md applies.
