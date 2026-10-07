# Risk-scoped Self CI certification

Status: certification record for issue #477.

This record certifies the combined #474, #475, and #476 workflow.

## Certified contract

- `.ci/tests.json` is the authoritative test catalogue.
- Alias expansion is one-level, deterministic, unioned, deduplicated, and
  fail-closed.
- Durable high-risk aliases live with issue lifecycle state.
- Issue verification always retains issue-owned groups and adds high-risk alias
  groups plus cheap invariant groups.
- Ordinary issue pull requests use issue-tier verification.
- Broad regression is an explicit tier selected when a dependency-complete
  umbrella outcome is ready, or earlier when broader risk warrants it.
- RepoWorkflow does not infer umbrella semantics from ticket title prefixes.
- Integration runs broad validation plus the authoritative platform/provider
  matrix.
- Authoritative `main` pushes always select integration.
- Documentation-only changes retain the fast path unless a stronger tier is
  explicitly requested.
- CI records the selected tier, groups where applicable, and selection reason.
- Release cannot be satisfied by issue or regression evidence.

The public TDD contract remains:

```text
rwf tdd red group NAME
rwf tdd green
```

`rwf tdd green` remains argumentless.  Runtime RED/GREEN implementation and
RED-recorded group execution remain owned by #54/#76 and are not claimed as
implemented by this certification.

## Live evidence

PR #484, head `07366fa3655f36105f2ac79fd34063ea48513cc6`,
ran Self CI #1027 as issue-tier verification:

- tier: `issue`;
- groups:
  - `invariant-self-ci-contract`;
  - `issue-476-staged-self-ci`;
- broad `validate`: skipped;
- argv-limit matrix: skipped;
- graph-renderer matrix: skipped;
- ticket-merge matrix: skipped;
- result: GREEN;
- workflow wall time: 36 seconds;
- selected group execution time reported by the runner: about 1 second.

PR #484 merged as
`c1fce7eda2a3749bf9f7ff58f0e4834e9c9937d7`.
Post-merge Self CI #1028 selected:

```json
{"tier":"integration","issue":null,"groups":[],
 "reason":"authoritative main integration candidate"}
```

That exact candidate passed broad validation, argv-limit probes on Ubuntu,
Windows, and macOS, graph-renderer probes on all three platforms, ticket-merge
probes on all three platforms, and release.  Stable tag `v0.1.118` resolves
to the same merged main commit.

The explicit regression tier is covered by the deterministic tier planner and
convergence tests.  Integration is a stronger execution tier and runs the same
broad validation plus integration-only platform probes.

## Evidence-strength rule

Evidence strength is monotonic:

```text
issue < regression < integration
```

A stronger successful run may satisfy a narrower verification requirement.
The reverse is forbidden.  In particular, issue-tier or regression-tier
evidence cannot authorize a release requiring integration evidence.
