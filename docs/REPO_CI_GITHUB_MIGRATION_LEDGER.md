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

## Explicit outstanding acceptance gates

1. Implement and verify `execute` under the provider interface, including
   required stage enumeration, exact input candidate and base binding,
   stage-specific genuine FAIL observations, missing/corrupt INCOMPLETE, and
   deterministic retry behaviour. It currently reports execution-unavailable.
2. Redirect the *actual* hosted GitHub CI machine paths through the assembled
   dispatcher/provider, not only through compatibility wrappers. Preserve old
   event, runner, materialize, validate and finalization behaviour until all
   equivalence tests pass.
3. Prove preparation, hosted stage execution, artifact publication/download and
   result consumption across separate GitHub Actions jobs for the same
   exact candidate and invocation, including negative/missing-result runs.
4. Verify normalized results and lifecycle classification remain core-owned and
   equivalent to existing local and hosted behaviour; no adapter-authoritative
   PASS/FAIL/INCOMPLETE.
5. Run assembled regression and platform/provider tests on the candidate SHA,
   confirm no duplicated provider logic remains, then record successor-ready
   evidence before closing issue #67. An issue-tier GREEN alone is not cutover
   certification.

The source PR is intentionally a draft. Completing any single individual
component does not satisfy these combined acceptance gates.
