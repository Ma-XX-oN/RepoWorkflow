# Issue #447 — experiment log

This log records the renderer verification investigation in a resumable form.
Each entry uses:

- Problem
- Hypothesis
- Action
- Result
- Learning / next step

## Experiment 1 — original escaped defect

**Problem**

A broad typed-ticket smoke reached physical rendering and failed semantic
geometry validation:

```text
rendered directed geometry changes semantic reachability for 'G350':
expected ['*F:A96'], got ['*F:A96', 'AU308', '✓AV318']
```

**Hypothesis**

A many-to-many fan bridge was allowing target-side merging before source-side
branching had separated, creating a false visual switch.

**Action**

Retained the real canonical typed-ticket path through `render_graph()`, added
a focused many-to-many fixture, and kept the independent geometry validator
strict.

**Result**

The original failure was reproduced.  Earlier #442 coverage had stopped at
`validate_graph()` and therefore never exercised physical routing.

**Learning / next step**

Do not stop escaped-defect confirmation at the repaired layer.  Continue
through downstream supported stages.

## Experiment 2 — verification-system hardening

**Problem**

The defect escaped despite GREEN historical renderer certification and
cross-platform probes.

**Hypothesis**

The verification system had multiple evidence gaps: missing many-to-many
cross-product coverage, stale certification reuse, synthetic platform probes,
and no assembled current-graph smoke.

**Action**

Documented reusable safeguards in `TEST_ADEQUACY.md`, RepoWorkflow-specific
rules in `GRAPH_RENDERER.md` / `TEST_STRATEGY.md`, and the escape analysis
in the #447 audit record.  Added:

- bounded generated DAG + lane-partition semantic tests;
- canonical typed-ticket full-render tests;
- assembled `rwf issue list` -> `rwf lanes select` smoke;
- certification binding to material graph/renderer inputs;
- current canonical graph rendering in the cross-platform probe;
- CI cancellation for obsolete PR candidates.

**Result**

The stronger tests immediately exposed downstream routing/search defects that
the old suite could not see.

**Learning / next step**

Treat production-owned graph data as an active fixture and keep semantic,
integration, platform, and assembled-workflow evidence distinct.

## Experiment 3 — adjacent many-to-many routing

**Problem**

A same-row adjacent edge that was both fan-out and fan-in could create false
reachability.

**Hypothesis**

The edge needed separate source-side and target-side tracks with an explicit
dogleg so branch-before-merge ordering was geometric, not incidental.

**Action**

Separated routing construction from the semantic oracle and introduced safe
dogleg routing for qualifying adjacent bridges.

**Result**

The original geometry failure moved downstream into long-route planning.

**Learning / next step**

The original defect was unmasked, but the assembled workflow still was not
complete.  Continue through long-route planning.

## Experiment 4 — long-route planning

**Problem**

Greedy per-edge long-route selection produced locally valid choices that could
make later edges impossible, then broad backtracking became too expensive.

**Hypothesis**

Long-route selection needed bounded global search, forward checking, semantic
candidate validation, and geometric conflict partitioning.

**Action**

Added:

- deterministic candidate enumeration;
- bounded backtracking;
- MRV / forward checking;
- switch-connected semantic candidate validation;
- long-bridge source/target track identity;
- safe disjoint long-row reuse;
- geometric-conflict partitioning;
- structural regressions for backtracking and conflict/reuse classes.

**Result**

Earlier candidates progressed from specific edge failures to bounded-search
exhaustion.  Subsequent branch history records a canonical renderer GREEN
milestone and later search-quality/certification hardening.

**Learning / next step**

Do not increase search bounds blindly.  Partition and rank according to actual
geometric conflict, then validate the final whole graph independently.

## Experiment 5 — current continuation state

**Problem**

The current #447 branch head is
`ea6543c45362b98c608bba6dce11b9630dc598d3`.  Branch history contains:

- canonical renderer GREEN milestone;
- stale-certification input record;
- refreshed renderer certification;
- version bump;
- escaped-defect closure safeguards.

PR #448 is ready for review but GitHub currently reports it not mergeable, and
the latest head has no current PR workflow run attached.

**Hypothesis**

The remaining work is integration closure rather than rediscovering renderer
semantics: current `main` has moved and the final verified branch must be
reconciled with it, then revalidated as the exact integration candidate.

**Action**

Next: inspect current `main`, branch/base divergence, conflicts, certification
bindings, and release-version lease.  Semantically merge any overlaps; do not
reuse earlier GREEN evidence after rebasing/merging.

**Result**

Pending.

**Learning / next step**

The exact integrated candidate must pass the strengthened verification system
before merge/release.
