# Issue #447 — renderer verification escape analysis

## Escaped defect

A broad typed-ticket smoke test reached the current renderer and failed with:

```text
rendered directed geometry changes semantic reachability for 'G350':
expected ['*F:A96'], got ['*F:A96', 'AU308', '✓AV318']
```

The canonical dependency graph was valid.  The failure was in physical routing:
a many-to-many fan bridge could create a merge-before-branch visual junction.

## Why existing verification missed it

1. The #442 repository-wide regression stopped at
   `validate_graph(projection.graph)`.  It did not continue through
   `render_graph()`, where the escaped defect lived.
2. Renderer fixtures covered fan-in and fan-out examples but did not treat the
   many-to-many source-degree x target-degree combination as a mandatory
   decision-table class.
3. Existing real-provider certification was historical evidence for older
   graph/renderer inputs and was not invalidated when ticket state,
   decomposition, projection, and selection semantics materially changed.
4. Cross-platform renderer probes used one synthetic graph.  Their GREEN
   status established portability of that fixture, not semantic coverage of
   the current RepoWorkflow graph.
5. The verification registry made universal-sounding claims such as unrelated
   crossings never creating semantic junctions while citing only a finite set
   of handcrafted examples.
6. #393 required every route candidate to satisfy independent semantic
   reachability validation, but candidate selection and final-layout validation
   were not traced closely enough to prove that literal contract.
7. After the first escaped failure was repaired, testing did not continue the
   same assembled workflow through downstream stages that had previously been
   unreachable.
8. The renderer and its oracle inferred physical junctions from semantic
   endpoint identity: any same-source or same-target overlap was treated as a
   switch.  That incorrectly turned perpendicular crossings on private
   doglegs/routes into branch or merge points.  Junction identity must come
   from actual routed geometry, not merely from semantic relationship names.
9. Search-space growth in both adjacent-track ordering and long-route planning
   was initially treated as a search problem.  The safer correction is to
   remove false interaction classes first: passive tracks do not belong in an
   adjacent semantic search, and private/non-interacting routes should not
   share a combinatorial search space.

## Permanent prevention changes

The reusable rules are now documented in `TEST_ADEQUACY.md`:

- escaped-defect regressions continue through downstream supported stages;
- interacting behavioural dimensions require explicit cross-product analysis;
- combinatorial systems use bounded generated/property tests when an
  independent oracle exists;
- production-owned canonical data is an active test fixture;
- historical certification must be bound to material inputs and becomes stale
  when they change;
- platform, semantic, integration, and assembled-workflow evidence remain
  distinct.

RepoWorkflow-specific renderer rules are documented in `GRAPH_RENDERER.md`
and `TEST_STRATEGY.md`:

- explicit 1:1, 1:many, many:1, and many:many fan classes;
- many:many branch-before-merge semantics;
- generated bounded DAG/lane coverage;
- current committed ticket graph through full rendering;
- assembled public-CLI smoke through the same boundary;
- certification invalidation for graph/renderer/decomposition drift;
- explicit cell-level tests distinguishing shared-direction junctions from
  perpendicular crossings;
- search scopes derived from actual semantic/geometric interaction rather than
  every track present in the same region.

## Closure requirement

Issue #447 is not complete merely when the observed #350/#96 layout succeeds.
The stronger verification system must be executable and GREEN first, and the
routing repair must then pass under it without weakening the independent
geometry validator.
