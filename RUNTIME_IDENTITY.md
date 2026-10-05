# Runtime Writer/Session Identity Invocation Contract

Status: authoritative invocation contract for supplying durable-mutation
provenance to an RWF execution.

This document extends [STATE_CONCURRENCY.md](STATE_CONCURRENCY.md).  That
contract defines what writer/session identity means and where it is required;
this contract defines how a production invocation supplies it.

## 1. Scope

This contract applies to RWF commands that perform, or can enter, semantic
transitions which mutate durable shared state.

It freezes only the invocation boundary.  Durable lifecycle semantics,
relationship semantics, authorization, CAS, and multi-record transaction
protocols remain owned by their existing contracts.

## 2. Authoritative production input

An invoking agent/process supplies identity through exactly these process
environment variables:

- `RWF_WRITER_ID` — stable identity for the logical writer across retries and
  separate executions by that writer;
- `RWF_SESSION_ID` — identity for one logical execution/session.

The environment is the sole semantic-transition input.  There are no CLI
identity flags, repository/worktree configuration keys, provider fields, or
fallback inference sources in semantic/core RWF.

For ordinary public CLI invocations, the public invocation layer may provision
the pair when and only when both variables are absent:

- writer identity is a generated opaque identifier persisted in clone-local Git
  common state under `.git/repoworkflow/` (or the equivalent Git common dir);
- session identity is a newly generated opaque identifier for that CLI
  execution.

This provisioning happens only for mutation-capable public commands, after
syntax acceptance.  Read-only/help paths do not create identity state.

Explicitly supplied environment values remain authoritative.  If exactly one
of the pair is supplied, invocation fails closed rather than synthesizing the
other.

## 3. Source and precedence

There is no precedence chain.

For a mutation-capable semantic transition, RWF reads the two variables from
the environment inherited by that process.  Both must be present and valid.

Semantic/core RWF must not fill, override, or derive either value from branch
name, worktree path, commit author, operating-system user, process ID,
ticket/provider payload, authentication material, or repository/worktree
configuration.

The public invocation layer's generated clone-local writer identifier is
provenance, not an inference about the human account or provider identity.  It
must not contain credentials or claim a GitHub/Git identity.

An explicitly supplied environment value is never silently replaced.

## 4. Validation boundary

Identity is validated once at the command-to-semantic-transition boundary,
before any durable mutation or mutation-dependent side effect begins.

The two raw environment strings are used to construct the canonical
`WriterIdentity(writer_id, session_id)` defined by the state-store contract.
Its validation rules are authoritative.  The invocation layer must not create
a second, weaker identity syntax.

Missing variables or any value rejected by `WriterIdentity` fail closed
before mutation.

A read-only command that does not enter a mutation-capable transition does not
require runtime writer/session identity merely because it can inspect records
that contain provenance.

## 5. Propagation

After validation, semantic transitions receive the constructed
`WriterIdentity` value.  They do not reread environment variables and do not
accept separate writer/session strings.

Nested semantic operations in the same logical execution receive the same
validated value.  Storage layers record that value only where their existing
provenance contracts require it.

Provider adapters may arrange the invoking process environment, but core RWF
sees only the two provider-neutral strings.

## 6. Retry and execution semantics

`RWF_WRITER_ID` identifies the logical writer, not an individual process.
An orchestrator reuses it for retries and later executions performed by that
same writer.

`RWF_SESSION_ID` identifies one logical execution/session.  A retry that is
part of the same logical execution reuses the same session identity.  A new
logical execution by the same writer uses a new session identity.

Process restart alone does not decide whether a session is new.  The invoking
orchestrator decides whether it is resuming the same logical execution or
starting another one and supplies the corresponding explicit session value.

Semantic/core RWF does not generate either identity.  The ordinary public
invocation layer may generate the clone-local/default identities described in
section 2 before entering the semantic boundary.

## 7. Failure behaviour

For a mutation-capable transition, any missing or malformed runtime identity
is an invocation error and fails closed.

Before returning that failure, RWF must not publish durable state, advance a
durable revision, create provenance using a substitute identity, or perform a
local/repository side effect that is semantically part of the rejected
transition.

Diagnostics identify which required identity input is missing or malformed
without searching for substitute identity sources.

## 8. Identity is not authorization

Possessing or choosing a writer/session identity grants no workflow authority.

Authorization, transition legality, expected revisions, relationship
preconditions, and transaction gates remain independent checks.  Matching the
writer/session identity on an existing record does not permit overwrite,
conflict bypass, or transition bypass.

Writer/session identity is provenance only.

## 9. Persistence rule

The invoking agent/process supplies opaque non-secret identifiers suitable for
durable audit provenance.  Authentication material is not an identity source
and must not be deliberately supplied as either identity.

RWF persists only the validated identity strings required by existing durable
provenance contracts; it never persists the surrounding process environment.

## 10. Consumer obligations

The runtime identity implementation in #186 must:

1. read exactly `RWF_WRITER_ID` and `RWF_SESSION_ID`;
2. construct one canonical `WriterIdentity` before mutation-capable semantic
   work begins;
3. fail closed when either input is absent or canonical validation rejects it;
4. pass the resulting object through semantic transitions rather than allowing
   those transitions to infer or reread identity; and
5. prove by tests that read-only commands do not acquire an unnecessary
   identity requirement.

#185 and #64 consume this contract through #186.  They do not define alternate
identity sources.
