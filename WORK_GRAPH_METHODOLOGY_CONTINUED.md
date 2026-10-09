## 14. Use decomposition to expose architecture problems

During issue refinement, treat the following as diagnostic signals:

- a leaf both defines a contract and consumes it;
- a presentation command blocks a non-presentation consumer;
- provider-specific mechanics appear in portable semantics;
- one issue contains both read-only planning and mutation;
- one state issue simultaneously owns storage layout, concurrency, recovery,
  and domain records;
- several unrelated outcome containers describe the same loose leaves;
- cleanup happens long after creation but lives in the same leaf;
- an "active issue" is represented as one shared mutable global value;
- a high-level dependency exists only because one implementation ticket consumes another;
- dependency descriptions repeatedly use "sort of", "through", or "indirectly".

These are reasons to inspect boundaries, not automatic reasons to create more
issues.  Split only when a cleaner independently testable contract appears.

## 15. Testing and refinement companion

Verification procedures and acceptance checklists are defined in
[WORK_GRAPH_TESTING.md](WORK_GRAPH_TESTING.md); public-workflow first-use
ownership is governed by `FIRST_USE_WORKFLOWS.json` and `TEST_STRATEGY.md`.
