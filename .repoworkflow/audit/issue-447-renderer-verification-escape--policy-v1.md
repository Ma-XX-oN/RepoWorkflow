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

## Work checkpoint — current #448 head

Current branch head:

```text
5a5a4663e9728ef396ca4ddadb08f1fe7834ee1d
```

PR #448 remains draft and mergeable against main
`4e1e45af5e5482378bd78534371efe9e11be37e3`.

Latest active CI is Self CI run #945
(`37567540283`) for this exact head.

Work already completed before this checkpoint includes:

- canonical typed-ticket full-render smoke wired into the cross-platform
  renderer probe;
- assembled public `rwf issue list` -> `rwf lanes select` smoke;
- bounded generated four-node DAG coverage crossed with valid lane path
  partitions;
- explicit one:one, one:many, many:one, and many:many fan-degree coverage;
- certification-input binding for canonical graph and renderer modules;
- stale-PR-run cancellation through workflow concurrency;
- candidate semantic validation over switch-connected geometry;
- bounded backtracking/MRV/forward checking for long-route planning;
- long-row reuse only for geometrically compatible spans;
- many:many adjacent/long bridge separation work;
- source modules split so renderer/routing/oracle files remain below the
  repository 500-line limit.

Important previously observed failures, in order:

1. #442 stopped before physical rendering and missed false reachability from
   G350 to AU308/AV318.
2. After full rendering was added, long-route planning failed for AL231->AL235.
3. Global long-route search then exhausted its bounded state space.
4. Search was partitioned/refined by geometric conflicts.
5. Subsequent work shifted to boundary ordering/quality and same-row dogleg
   separation.

Recent commits after the long-route work include:

- separate opposing same-row dogleg track groups;
- reserve passive separators for same-row fan doglegs;
- choose best semantically valid boundary ordering;
- stop boundary search at perfect quality;
- bind certification to the complete renderer module surface;
- require mechanically complete certification bindings;
- rank boundary candidates before semantic validation.

Do not redo the above work without first identifying a regression in those
specific mechanisms.  Continue from the exact current head and the latest
authoritative CI failure/result.

### Milestone: canonical renderer cross-platform GREEN

Semantic candidate `5a5a4663e9728ef396ca4ddadb08f1fe7834ee1d`
passed the strengthened canonical graph renderer probe on Ubuntu, Windows, and
macOS in Self CI run #945.  Ticket-merge and argv-limit probes were also GREEN.
Authoritative `validate` was still in progress at the time of this checkpoint.

This is the first candidate in the #447 work where the current committed typed
Initiative/Epic/Feature graph completed full rendering successfully on all
three supported CI platforms.

### Certification binding status after renderer GREEN

The certification binding is intentionally stale at this stage.  Exact stale
material inputs against head `e2251fa40d48321badb6629e56db4e0ec9d7fb5a`:

- `.repoworkflow/tickets.csv`
- `repo_workflow/graph_render.py`
- `repo_workflow/graph_layout.py`
- `repo_workflow/graph_geometry.py`
- `repo_workflow/graph_long_routes.py`
- `repo_workflow/graph_boundary_plan.py`
- `repo_workflow/graph_boundary_order.py`
- `repo_workflow/graph_routing.py`

This is expected and demonstrates that old certification evidence is not being
silently reused.  Do not refresh these digests until the current renderer
candidate has passed the semantic/canonical verification gates.

### Authoritative pre-certification validation result

Self CI run #948 tested semantic head
`d34c81b2f23931f0164c01d9921aa4dfcaa2f6a6`.

Results before certification refresh:

- canonical renderer probe: GREEN on Ubuntu, Windows, and macOS;
- ticket-merge probe: GREEN on Ubuntu, Windows, and macOS;
- argv-limit probe: GREEN on Ubuntu, Windows, and macOS;
- authoritative validation executed 652 tests in 272.362 seconds;
- exactly two tests failed;
- both failures were the intentionally stale renderer-certification binding:
  material-input digests no longer matched and the manifest did not yet cover
  the mechanically complete current `graph_*.py` renderer module surface;
- no renderer, generated-DAG, assembled CLI, canonical-graph, ticket-state, or
  other regression test failed.

The subsequent certification refresh at
`97b6de2c993e564c9a32d90a3e34ec7163fc77d8` bound all 18 material inputs
and recorded run #948 as evidence.  VERSION was then advanced to 0.1.113 at
`e14ba274bb77b09bc9c514f93c828cd3dffcc835`.

