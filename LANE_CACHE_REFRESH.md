# Lane Cache and Refresh Semantics

Status: authoritative contract for provider access during lane selection and
inspection.

## 1. Local-first default

The canonical synchronized ticket state is the operational dependency source
between synchronization boundaries.

Without `--refresh`, lane selection discovers the complete connected component
from known canonical nodes locally.  The ticket dependency provider is queried
only when a requested node or a prerequisite reached while acquiring missing
state is absent from synchronized ticket state.

Repeated selection of the same known component therefore performs no dependency
provider reads.

`lanes select remove` is entirely local without `--refresh`.

## 2. Explicit refresh

`--refresh` is the explicit provider reread boundary for lane commands.

For selection mutations, refresh scope is the requested or resulting selected
connected component.  It is not a repository-wide crawl.

During refresh:

- provider dependencies are reread for every currently known node in the
  relevant connected component;
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

Known portions of the component are reused without rereading the provider.

## 4. Authority and failure

The provider is authoritative only at explicit synchronization/refresh
boundaries or when local dependency data is genuinely absent.

Provider failure is never interpreted as an empty dependency set.

Runtime never infers dependency edges from title prefixes, ticket-body grouping,
or Git ancestry.

## 5. Verification obligations

Tests must distinguish requirements coverage from structural coverage and
prove at the public CLI boundary:

- first acquisition performs provider reads for missing nodes;
- identical repeated selection performs zero new provider reads;
- adding a focus seed reads only newly missing prerequisite nodes;
- removing a root performs zero provider reads by default;
- restart preserves cache reuse;
- cached selection succeeds when the provider is unavailable;
- `--refresh` rereads only the relevant connected component;
- refresh conflict/provider failure leaves ticket state and selection unchanged;
- remove-refresh excludes removed-only nodes;
- provider fixtures conform to the independently verified adapter contract.

All applicable TEST_ADEQUACY.md state/lifecycle and failure requirements apply.
