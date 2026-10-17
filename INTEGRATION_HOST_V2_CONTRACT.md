# Integration host V2 — #681

Status: DRAFT, PARTIAL. Existing repo-host v1 six-operation protocol remains unchanged.

## Operations

- `refs.list`: discover exact READY PRELIM refs; require complete provider pagination.
- `ref.create`: idempotently create an INT-ATTEMPT ref, not a PRELIM ref.
- `ref.cas`: update only an INT-ATTEMPT ref with expected-old SHA.
- `lease.read` / `lease.cas`: authoritative one-active-coordinator-per-destination lease, never a clone-local lock.
- `attempt.read` / `attempt.record`: durable readback and terminal/deferred result publication.

V2 requests carry schema version, repository, operation, request ID and parameters. Strict typed results echo the same identity. UNKNOWN mutations require provider readback before any retry. Published PRELIM branches are immutable READY submissions; no separate queue branch/file.

## Verified versus outstanding

Provider-neutral protocol negative tests and mocked GitHub ref inventory/create tests passed locally. GitHub `refs.list` pagination beyond the first page, live INT-ATTEMPT creation, remote `ref.cas`, lease CAS, terminal persistence, expired-grant refusal, and hosted certification are NOT verified. The provider implementation MUST refuse unsupported operations.

Disposable repository experiment: isolated `rwf681-cas-20261017-1849` began at `b411d215bec5c62c8a3ca3062ec8f8743f2d7299` and advanced to `890d585f0ec4e74c5657bcbd25928309d76d72ab`. A mismatched expected-SHA update yielded a GitHub GraphQL error rather than a clear stale-ref rejection; readback showed the new commit persisted. Result: INCOMPLETE, not PASS. Keep disposable branch isolated until supported deletion/cleanup.

Final provider acceptance must prove destination-tip CAS at merge time, permission checks, exact candidate/test/version binding, competing writers, readback after unknown responses, deferred MIT distinct from FAIL, recovery, and safe cleanup. #85/#86/#676 hard security remains deferred. No production merge or protected tag authorization.
