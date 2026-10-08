# Lane Cache and Refresh Semantics

Status: authoritative contract for provider access during lane selection and
inspection.

## 1. Local-first default

The canonical synchronized ticket state is the operational dependency source
between synchronization boundaries.

Lane selection persists explicit include and exclude rules. Each rule contains
a seed and one projection mode:

- `single`;
- `dependencies`;
- `dependents`;
- `both`.

`both` is the union of two independent traversals started at the seed. It is
not an undirected connected-component crawl and does not reverse direction after
leaving the seed.

Without `--refresh`, known synchronized state is reused and the dependency
provider is queried only when data required by the requested rule projection is
missing.

## 2. Explicit refresh

`--refresh` is the explicit provider reread boundary for lane commands.

Refresh scope follows the persisted projection rules:

- `single` refreshes the seed plus any support records required to keep
  canonical synchronized state structurally valid;
- `dependencies` follows dependencies only;
- `dependents` follows dependents only, while acquiring prerequisite support
  records when canonical graph validity requires them;
- `both` is the union of those two seed-origin directions;
- exclusion rules are acquired with the same projection semantics.

Support-only acquisition never places a node in the visible lane projection.

During refresh:

- identical local/provider dependency sets are idempotent;
- an empty local set may be populated from a non-empty provider set;
- differing non-empty sets fail closed and require explicit dependency
  synchronization/reconciliation;
- provider failure aborts before lane-selection mutation;
- the prior synchronized ticket state and selection remain valid after failure.

## 3. Missing local data

A missing rule seed is not treated as stale or empty. RWF queries the configured
provider for that seed, validates the result, and continues only in the
direction required by the projection rule.

When a fetched node names dependencies that are required for canonical graph
validity, those support records are acquired as needed. Their acquisition does
not change projection membership.

## 4. Authority and failure

The provider is authoritative only at explicit synchronization/refresh
boundaries or when required local relationship data is genuinely absent.

Provider failure is never interpreted as an empty dependency set.

Runtime never infers dependency edges from title prefixes, ticket-body grouping,
or Git ancestry. `Initiative:`, `Epic:`, `Feature:`, `Bug:`, and
`Refactor:` are presentation classifications, not traversal semantics.

## 5. Persisted selection intent

The worktree-local lane selection stores deterministic include and exclude
projection rules together with derived closure, graph revision, and lane
assignment.

Legacy root-only selection records migrate each root to mode `both`; legacy
focused-traversal policy fields are not part of the current selection contract.

`select` replaces include rules. `add` adds include rules. `remove`
removes the matching seed-plus-mode include rule. `exclude` adds subtraction
rules. Derived membership is recomputed from current synchronized state.

## 6. Verification obligations

Tests must distinguish requirements coverage from structural coverage and prove
at the public CLI boundary:

- cold acquisition follows the requested direction;
- default `both` never reverses direction away from the seed;
- support-only acquisition does not enter the projection;
- repeated selection reuses synchronized state;
- restart preserves projection rules;
- explicit refresh replays the persisted directional rules;
- provider conflict/failure leaves ticket state and selection unchanged;
- include/exclude overlap is deterministic;
- legacy selections migrate deterministically;
- `--count` equals final projected cardinality without rendering;
- provider fixtures conform to the independently verified adapter contract.
