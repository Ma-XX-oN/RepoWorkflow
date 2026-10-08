# Lane Cache and Refresh Semantics

Status: authoritative contract for provider access during lane selection and
inspection.

## 1. Local-first default

The canonical synchronized ticket state is the operational dependency source
between synchronization boundaries.

Without `--refresh`, lane selection uses synchronized local state first.
With no persisted `--follow` policy, the projected selection contains only the
explicit roots and ordinary dependency/dependant traversal does not start.
Missing direct dependency targets may still be acquired as support-only
canonical state so the synchronized dependency graph remains structurally
complete; those support nodes do not enter the projected lane selection merely
because they were acquired.

When a persisted `--follow` policy enables traversal, discovery proceeds
through known canonical dependencies and dependants subject to its group-boundary
budgets.  The ticket dependency provider is queried only when a requested,
traversable, or structurally required support node is absent from synchronized
ticket state.

Repeated selection of the same known projected state therefore performs no new
dependency provider reads.

`lanes select remove` is entirely local without `--refresh`.

## 2. Explicit refresh

`--refresh` is the explicit provider reread boundary for lane commands.

For selection mutations, refresh scope is the requested or resulting selected
projection under the persisted traversal policy, plus support-only dependency
targets required to keep synchronized canonical state valid.  It is not a
repository-wide crawl.  Refresh preserves per-path consumed follow budgets; it must not reset a
boundary allowance merely because a reached node is already cached.

During refresh:

- provider dependencies are reread for every currently known traversed node in
  the relevant projection, plus required support-only dependency targets;
- identical local/provider sets are idempotent;
- an empty local set may be populated from a non-empty provider set;
- differing non-empty sets fail closed and require explicit dependency
  synchronization/reconciliation;
- provider failure aborts before lane-selection mutation;
- the prior synchronized ticket state and selection remain valid after failure.

For `select remove ... --refresh`, the removed root is excluded from refresh
unless it remains reachable from another selected root.

## 3. Missing local data

A missing requested node is not treated as stale or empty.  RWF queries the
configured dependency provider for that node, validates the result, adds the
node atomically to canonical state, and continues through any newly discovered
missing dependencies.

Known projected and support-only portions are reused without rereading the
provider.

## 4. Authority and failure

The provider is authoritative only at explicit synchronization/refresh
boundaries or when local dependency data is genuinely absent.

Provider failure is never interpreted as an empty dependency set.

Runtime never infers dependency edges from title prefixes, ticket-body grouping,
or Git ancestry.

## 5. Persisted traversal policy

The worktree-local lane selection stores normalized traversal policy together
with roots, closure, graph revision, and lane assignment.  This includes both
`--follow` budgets and `--show-children` context.  Subsequent
`lanes view --refresh` operations reuse both policies.

Older selection records remain readable and project the corresponding policy
defaults: schema 1 has no follow or show-children policy; schema 2 has follow
policy but no show-children policy.  An absent/default follow policy means
ordinary traversal is disabled.

Selection `add` and `remove` preserve the existing policies when no
replacement traversal flags are supplied.  A stopped matching group may acquire
and display one immediate adjacent layer for `--show-children`, but those
display-only nodes never restart ordinary provider traversal.

## 6. Verification obligations

Tests must distinguish requirements coverage from structural coverage and
prove at the public CLI boundary:

- first acquisition performs provider reads for missing nodes;
- identical repeated selection performs zero new provider reads;
- adding a focus seed reads only newly missing prerequisite nodes;
- removing a root performs zero provider reads by default;
- restart preserves cache reuse;
- cached selection succeeds when the provider is unavailable;
- no-follow selection keeps support-only acquisition out of the visible
  projection;
- `--refresh` rereads only the relevant followed projection and required
  support state;
- refresh conflict/provider failure leaves ticket state and selection unchanged;
- remove-refresh excludes removed-only nodes;
- provider fixtures conform to the independently verified adapter contract.

All applicable TEST_ADEQUACY.md state/lifecycle and failure requirements apply.
