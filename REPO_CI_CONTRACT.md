# Portable repo-ci semantic contract (v1)

Status: frozen interface for #65; implementation belongs to #91-#94.
This document defines the semantic boundary, not adapter selection or execution.

## Authority and boundaries

Core RepoWorkflow supplies the exact candidate identity, required validation
stages, legal lifecycle transitions, authorization and current-base policy.
Core alone classifies PASS, FAIL, or INCOMPLETE and decides whether evidence
permits a transition or terminal tag. An adapter supplies observations and
performs declared mechanics; it never decides semantic success or publishes
terminal state on its own.

The caller of `repo-ci` supplies an operation and versioned request envelope.
The forwarder in #91 resolves the configured adapter deterministically and
forwards the envelope unchanged. No provider name, event, runner label, or
transport payload is part of this interface.

## Common request envelope

All operations accept a structured request with:

- `contract_version`: exactly `1`; unknown versions are rejected.
- `operation`: one of the operations defined below.
- `invocation_id`: nonempty opaque identity for this attempt.
- `candidate`: exact repository identity, immutable commit identity, and
  relevant base identity as supplied by core; no adapter-derived substitution.
- `requirements`: explicit required stages, capabilities and artifact
  declarations, including an empty collection when none is required.
- `inputs`: operation-specific structured arguments.

Unknown mandatory fields, missing identities, malformed values, or conflicting
requirements yield a structured error; no implicit defaults invent authority.
Identity fields are opaque strings, compared exactly, not interpreted as names.

## Operations

| Operation | Inputs | Normal output |
| --- | --- | --- |
| `inspect-context` | execution context, requested mode | normalized execution mode and observed context |
| `resolve-capabilities` | required capabilities and constraints | available capabilities, unsatisfied requirements |
| `prepare` | selected requirements, execution context | preparation observations and unmet prerequisites |
| `execute` | stage IDs, immutable candidate, execution inputs | per-stage observations and execution diagnostics |
| `publish` | exact-bound evidence and declared artifacts | immutable receipt/locator and publication observations |
| `fetch` | evidence locator, expected identities | retrieved evidence bytes/metadata and integrity observations |
| `check-policy` | declared policy requirements and context | per-requirement observations and diagnostics |

Operations are independent requests. A `publish` receipt is not a PASS
certificate; `fetch` does not implicitly accept or certify retrieved evidence.
`execute` does not mutate core lifecycle state. `check-policy` is read-only.
Any artifact writes are confined to the explicit `publish` declaration.

## Common response envelope

Each response contains `contract_version`, `operation`, `invocation_id`,
the exact `candidate` received, `status` (`ok` or `error`), `observations`,
`diagnostics`, and `artifacts` (possibly empty). Operation-specific outputs
are inside `observations`. Every stage observation identifies its stage,
candidate, completion state, and observed test outcome independently.

An adapter must never emit a core terminal classification as its authority.
The core maps complete, authentic, identity-matched, requirement-satisfying
observations to PASS; a complete genuine test rejection to FAIL; and absent,
incomplete, invalid, mismatched, unavailable, or untrusted observations to
INCOMPLETE. A transport failure is not a test failure. A failed required
preparation or missing capability is INCOMPLETE, not FAIL.

## Errors and capabilities

Errors have stable semantic codes: `invalid-request`,
`unsupported-version`, `unsupported-operation`,
`capability-unavailable`, `prerequisite-unavailable`,
`execution-unavailable`, `transport-failed`, `identity-mismatch`,
`integrity-failed`, and `internal-error`. Diagnostics may carry opaque
provider detail, but consumers branch only on the semantic code.
An error response never supplies successful completion evidence.

Capabilities are explicitly enumerated with availability and constraints.
Unknown, missing, or conflicting required capabilities fail closed. Optional
capabilities cannot silently satisfy required ones. An adapter cannot upgrade
an observed partial result to complete by omitting a required stage.

## Equivalence and identity

For identical candidate, requirements and observations, local and hosted
execution MUST yield the same core classification and lifecycle eligibility.
Provider transport and execution scheduling are not semantic inputs. The
adapter must round-trip exact candidate, invocation, stage, artifact identity
and integrity metadata through publication and retrieval. A missing, stale,
corrupt or cross-candidate result cannot satisfy a required stage.

Retries are separately identifiable invocations. Repeating a fetch is
read-only. Repeating a publish with the same identity and identical content is
idempotent or returns an explicit conflict; different content under the same
identity must never silently replace prior evidence. No operation authorizes
merging, terminal tagging, or production cutover.

## Contract acceptance matrix

The implementations in #91-#94 must demonstrate:

1. Valid zero/one/many stage and capability requests, including empty
   optional artifacts, preserve the request and response identities.
2. Unknown operation/version, absent candidate, conflicting capabilities,
   and malformed envelopes fail without side effects.
3. Complete required success, genuine test failure, incomplete execution,
   missing stage, unavailable capability and transport error produce the
   expected distinct core classifications.
4. Published and fetched evidence preserves bytes, identity, integrity,
   completeness and stage membership; tampering and stale candidates fail.
5. Retries, duplicate publication, conflicting publication and changed
   candidate/base do not reuse invalid evidence.
6. Local and hosted fixtures with the same normalized observations have
   identical core classification and transition eligibility.
7. The forwarder does not choose an adapter based on request content or
   reinterpret semantic arguments; provider-specific mapping remains within
   the adapter.

These are black-box requirements. Structural tests additionally verify that
provider-specific names and execution mechanics do not enter core semantics.
