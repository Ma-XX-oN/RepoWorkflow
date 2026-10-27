# Repository-host mutation v1 acceptance matrix

Issue: #81.  Consumers: #119 dispatcher, #97 GitHub adapter, #84 integration.

This matrix is normative for implementations.  Tests here specify expected
external behaviour independently of adapter internals.  Documenting these
cases performs no repository-host mutation.

| ID | Input / state | Required result |
| --- | --- | --- |
| B01 | Capability query with empty parameters | Exact read-only operation map; unchanged |
| B02 | Required operation absent or false | No mutation; unsupported |
| B03 | Valid single issue update | Applied; matching number/title/state |
| B04 | Same update repeated with same request ID | Unchanged or same authoritative result; no duplicate effect |
| B05 | Same request ID, different title/state | Conflict; no mutation |
| B06 | Update non-existent issue | Not found; no issue creation |
| B07 | Zero, negative, bool, or string issue number | Invalid request |
| B08 | Comment once and retry after adapter restart | One comment and identical opaque comment identity |
| B09 | Timeout after possible comment creation | Reconcile exact request, or unknown outcome without replay |
| B10 | Create PR once and retry | One PR, same number/head/source/target |
| B11 | Reuse creation request ID after source head changes | Conflict; no new PR |
| B12 | Update PR with stale expected head | Conflict; no mutation |
| B13 | Update PR with omitted field vs explicitly empty body | Preserve omitted; clear explicitly supplied body |
| B14 | Create/update PR with unauthorized merge-like change | No merge or finalization |
| B15 | Merge with changed tested head | Conflict; no merge |
| B16 | Merge with changed destination tip | Conflict; no merge |
| B17 | Merge when provider cannot atomically enforce target freshness | Unsupported; no merge |
| B18 | Merge with missing/expired/revoked authorization | Unauthorized; no merge |
| B19 | Merge with forged/stale eligibility reference | Unauthorized or conflict; no merge |
| B20 | Check publication with unverified claimed success | Unauthorized; no trusted success check |
| B21 | Check publication with authenticated terminal failure | Publish failure only at authorized context |
| B22 | Requested required context not authorized | Unauthorized; no check mutation |
| B23 | Schema version other than integer 1 | Invalid request |
| B24 | Malformed JSON; missing/extra envelope or operation parameter | Invalid request |
| B25 | Noncanonical repository, invalid request ID, malformed SHA | Invalid request |
| B26 | Valid envelope with wrong response operation/repository/request ID | Invalid response; caller fails closed |
| B27 | Success exit with malformed/extra result fields | Invalid response; caller fails closed |
| B28 | Missing/expired credentials or insufficient permission | Unauthenticated/unauthorized, not unchanged |
| B29 | Rate limit / network outage / ambiguous provider response | Distinct rate_limited/transport_failure/unknown_outcome |
| B30 | Concurrent same-ID requests | At most one side effect; other receives same result or conflict |
| B31 | Zero mutation requests | No adapter-host mutation |
| B32 | Many independent request identities | Exactly corresponding independent effects |
| B33 | Unrecognized operation and unavailable adapter | Unsupported or explicit invocation failure, never success |
| B34 | Adapter exit nonzero with structured error on stderr | No success JSON on stdout; exact identity/error schema |
| B35 | Adapter returns normalized success but mutates local Git state | Contract violation |
| B36 | Provider-specific payload fields in core request/result | Invalid request/response, not tolerated |

## Test levels and owners

- Contract conformance for the dispatcher (#119): fake executable exercising
  request serialization, exit/status/identity validation, malformed outputs,
  error preservation, capabilities, and explicit no-provider fallback.
- Adapter/provider conformance (#97): real sandbox issue/PR/comment and
  authorized check tests, replay across restart, permission denials, and
  stale-head/target rejection.
- Integration (#84/#85/#104/#542): exact accepted candidate binding,
  destination acceptance-time freshness, explicit remote-finalizer authority,
  and actual remote protection.  A GREEN local probe never substitutes for
  those server-enforced tests.

## Scope and evidence rule

#81 freezes interface semantics only.  It must not claim passing live provider
tests before #97/#85 implement and run them.  A successor reports each test
with candidate SHA, environment/provider version, fixtures, test groups,
observed output, and durable CI evidence.  Missing hosted evidence is
INCOMPLETE, not PASS.
