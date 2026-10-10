# repo-ci GitHub migration ledger (#67)

This document distinguishes staged provider wiring from actual CI cutover.

## Completed on the #67 work branch

- #65's portable operation/result contract is preserved.
- #91's public `repo-ci` dispatcher selects exactly one configured executable;
  `.ci/repo-ci.json` now binds that executable to the GitHub provider.
- The #92 GitHub mapping implements inspect-context, resolve-capabilities and
  prepare using portable request/response envelopes.
- #93's publish/fetch bundle transport verifies exact candidate, invocation
  and declared artifact identities, bytes and integrity. It cannot certify PASS.
- #94's check-policy operation inspects canonical workflow bootstrap read-only.
- Legacy `github-*` CLI entrypoints now import provider-owned compatibility
  wrappers; their original observable outputs remain unchanged. Equivalence
  tests compare the wrappers against the still-authoritative old implementation.
- Existing hosted workflows are not silently rewritten. No production, main
  branch, terminal tag or release mutation is authorized by this migration.

## V3 migration continuation (2026-10-10)

- The provider-neutral dispatcher resolves its installed adapter from the
  verified `RepoWorkflow/` consumer installation when the consumer has no
  explicitly configured adapter. A consumer-owned configuration takes
  precedence; unrelated workspaces retain fail-closed missing-config behaviour.
- The GitHub provider executes declared catalogue stages and the existing
  core consumer validators with checked-out commit and base identity checks.
  PASS/FAIL/INCOMPLETE is still produced by the core result engine, never
  invented by the provider. Empty/missing/unknown stage declarations, extra
  capabilities, changed identity and unsafe result paths are rejected.
- The actual reusable `consumer-ci.yml` machine paths now obtain mode,
  runner matrix and preparation context through the configured dispatcher
  and provider-owned compatibility layer. Core repository/branch policy,
  preflight, artifact materialization and the authoritative finalizer remain
  core operations with their prior behaviour.
- Consumer validation now enters through `repo-ci execute`. Provider result
  packaging uses `repo-ci publish`; each matrix job uploads its exact-bound
  bundle via GitHub Actions. The finalization job downloads these bundles and
  calls `repo-ci fetch` for integrity, candidate, base and invocation checks
  before giving results to the unchanged core finalizer.
- Tests exercise genuine core PASS, FAIL and INCOMPLETE, stable and development
  branches, zero/one/many catalogue stages, changed identity, rejected unsafe
  result paths, cross-process consumer dispatch, mode/matrix/preparation output
  equivalence, corrupt artifact rejection, and missing result fail-closed
  behaviour. The staging jobs demonstrate actual cross-job upload/download.
- The full regression now has its own issue-specific hosted certification
  workflow. Issue-scoped GREEN is explicitly distinct from the full suite.
- Existing legacy CLI surface remains as compatibility shims because the
  consumers still require those output formats. The provider owns these
  mechanics, while stable tags and lifecycle classification remain core-owned.
- No PR merge, main-branch mutation, terminal tagging, production cutover or
  release is authorized or performed by this branch.

## Acceptance gate evidence

1. **Execute observations:** consumer core-result parity and hosted stage
   execution are covered by issue-scoped and multi-platform test groups.
2. **Legacy CI entrypoints:** consumer mode, matrix, preparation, stage
   execution and result transport are routed through the provider; core
   semantic operations retain their prior authority.
3. **Cross-job transport:** the hosted dispatcher and transport workflows
   exercise exact-bound publication/retrieval and stale identity rejection.
   Consumer-fixture tests also exercise provider transport and corruption.
4. **Core-owned classifications:** the consumer validator writes the
   original structured results; the provider neither writes terminal status
   nor tags. Missing/corrupt transport never produces accepted evidence.
5. **Assembled regression:** pending verification against the final exact
   candidate SHA. Record the full hosted run's conclusion before DONE.

Any failed or skipped check must be resolved or reported with its exact
remaining condition. Do not close #67 or claim successor readiness until
all five gates have current, exact-candidate evidence.

The source PR is intentionally a draft. Completing any single individual
component does not satisfy these combined acceptance gates.
