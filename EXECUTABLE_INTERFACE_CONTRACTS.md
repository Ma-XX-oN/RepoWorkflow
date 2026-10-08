# Executable Interface Contract Proposal

Status: proposal owned by epic #487 for repository-neutral interface-first
decomposition, deterministic contract verification, replay, and cross-language
bindings.

This proposal extends the interface-oriented decomposition described by
[WORK_GRAPH_METHODOLOGY.md](WORK_GRAPH_METHODOLOGY.md) and
[WORK_GRAPH_TESTING.md](WORK_GRAPH_TESTING.md).  It does not replace either
document while this proposal remains non-authoritative.

## 1. Purpose

Some dependency chains exist only because a provider implementation and one or
more consumers need to agree on an interface.

For example:

```text
grammar -+- implement tab completion
         |
         +- implement some other feature
```

The consumers do not fundamentally need the finished grammar implementation.
They need an agreed interface that the grammar provider promises to implement.

Extracting that interface first changes the work graph to:

```text
                  interface contract
                  /       |       \
                 v        v        v
              provider consumer1 consumer2
                 \        |       /
                  \       |      /
                   integration
```

The provider and consumers can then proceed in parallel.  Each side can also
be tested independently against the same executable contract.

The central principle is:

> A provider and its consumers agree on an explicit interface before parallel
> implementation begins.  Provider and consumer tests execute the same
> deterministic interface contract from opposite sides.

RepoWorkflow must not infer whether an interface is stable enough for parallel
work.  The tickets define that agreement.

The benefit is broader than execution speed.  Defining the contract before
coding makes architecture and behavioural assumptions independently testable.
Tests and scenarios can expose ambiguity, missing cases, awkward APIs, and
fragile sequencing before implementation.  The same discipline improves serial
work and also enables speculative execution.

## 2. Contract ticket and implementation tickets

The interface contract is a first-class work product.

Once a contract ticket is accepted:

- the provider ticket implements the contract;
- consumer tickets implement against the contract;
- provider and consumers are parallel-ready;
- integration waits for all required implementations;
- provider failures do not invalidate consumers when the contract is unchanged;
- contract changes are explicit revisions requiring affected revalidation.

For the grammar/completion example, the contract specifies the information that
completion receives from the object representing the current CLI parse.  It
must be precise enough for completion to be implemented and tested without the
real parser implementation.

The graph should therefore represent:

```text
contract
  +-- provider implementation
  +-- consumer implementation
  +-- other consumer implementation
        |
        v
integration/certification
```

rather than a false provider-then-consumer dependency.

## 3. Executable contract

The interface must be scriptable.

Prose remains useful for rationale and ownership, but observable call behaviour
also needs a deterministic executable representation.

A scenario is an ordered stream of expected events, for example:

```text
call create_parser(["lanes", "select"]) -> $parser
call $parser.current_node() -> ...
call $parser.valid_next() -> ["--help", "403", "404"]
```

The stream may contain:

- free-function calls;
- member-function calls;
- expected arguments;
- expected return values;
- expected errors;
- symbolic object references;
- captured results reused by later calls;
- deterministic ordering and cardinality.

The contract script must not depend on provider implementation behaviour.

## 4. Comparing stream

The runtime is centred on one comparing stream:

```text
InterfaceContract
      |
      v
ComparingStream
      |
      v
InterfaceRunner
```

The stream is the ordered source of truth for both provider verification and
consumer replay.

During one execution the stream is immutable.  Runtime state consists of the
current position, captured symbolic values, and any in-flight call.

A mismatch should identify the exact stream event, expected call, and observed
call.  This makes failures contract diagnostics rather than opaque mock
failures.

## 5. Provider verification

The real provider is verified with:

```text
preverify(...)
real call
postverify(...)
```

A forwarding helper may provide the usual integration point:

```text
fwd(...)
  -> preverify(...)
  -> invoke real function/member
  -> postverify(...)
  -> return real result
```

The wrapper must not alter successful provider behaviour.

### 5.1 preverify

`preverify()` checks the next expected call before provider code executes.

It verifies:

- expected stream event;
- free-function or member-function identity;
- symbolic receiver identity for member calls;
- argument count and values;
- captured references;
- call order;
- deterministic contract preconditions.

An unexpected call fails before the real function runs.

`preverify()` establishes an in-flight call but does not commit the event as
complete.

### 5.2 postverify

`postverify()` checks the provider outcome.

It verifies:

- expected return value or structured output;
- expected error or exception;
- output captures;
- deterministic contract postconditions.

Only successful post-verification advances past the call.  Unexpected results
or failures leave the mismatch associated with the in-flight event.

## 6. Consumer replay

Consumers use the same contract without the provider implementation.

`replay()`:

1. validates the expected function or member;
2. validates the receiver where applicable;
3. validates the consumer inputs;
4. obtains the scripted output or error;
5. applies captures and state transitions;
6. advances the stream;
7. returns or raises the scripted result.

Replay outputs come from the contract.  They are not generated by arbitrary
callbacks or copied from current provider behaviour.

Provider verification and consumer replay must share the same comparison,
capture, sequencing, and output semantics.

## 7. Shared comparison engine

`preverify()`, `postverify()`, and `replay()` must share one comparison,
capture, reference-resolution, sequencing, and scenario-completion engine.
There must not be separate interpretations of the contract for verification
and replay.  Exact internal function names are not fixed here.

## 8. Free and member functions

Provide distinct front ends for free functions and member functions while
sharing the same comparing-stream engine.

A free call is identified by its function and arguments.  A member call is
identified by its receiver, member, and arguments.  The member-function form
therefore receives the object/receiver unconditionally.

Conceptually:

```text
FreeFunctionRunner
  preverify(fn_name, ...)
  postverify(fn_name, ...)
  replay(fn_name, ...)

MemberFunctionRunner
  preverify(obj, fn_name, ...)
  postverify(obj, fn_name, ...)
  replay(obj, fn_name, ...)
```

## 9. Symbolic object identity

Contract scripts must not depend on process-specific addresses.

Objects use symbolic identities such as:

```text
$parser
$repo
$session
```

A call may capture an object and reuse it later:

```text
create_parser(...) -> $parser
$parser.parse(...)
$parser.valid_next(...)
```

Provider verification maps the real object to the symbolic identity.  Replay
supplies a replay-side representative associated with the same identity.

Object lifetime, aliasing, and related semantics remain binding-specific where
the common model is insufficient.

## 10. Values, errors, and portability

The common contract format should support a small deterministic value model:

- null/no-value;
- booleans;
- integers;
- floating-point values with defined comparison semantics;
- strings;
- ordered sequences;
- mappings/structured records;
- symbolic references;
- deterministic typed errors.

The model is not fully language-neutral.  Language neutrality is only an
approximation.

Runtimes differ in object identity, integer behaviour, references, ownership,
mutation, aliasing, exceptions, result objects, async semantics, and dispatch.

The goal is therefore:

> A common deterministic contract model with explicit per-language bindings and
> extensions where semantics cannot be faithfully normalized.

Bindings must expose significant semantic differences rather than hide them for
the sake of apparent portability.

## 11. Deterministic matching

Contract scripts must be wholly deterministic.

The core format must not embed arbitrary host-language predicates or arbitrary
callbacks for matching.

Prefer specified operations such as:

- exact scalar equality;
- exact ordered sequence equality;
- exact mapping equality;
- selected structured-field matching;
- explicit type/category constraints;
- symbolic-reference identity;
- explicit deterministic numeric constraints;
- explicit expected errors.

Richer matching should be added as named, specified contract operations.

## 12. Scenarios and lifecycle

An interface normally needs multiple scenarios, including ordinary, empty,
dynamic, invalid-input, provider-error, repeated-operation, and changed-state
cases.  Each scenario has an independent comparing stream.

Scenario completion detects:

- missing expected calls;
- extra calls;
- wrong call order;
- wrong receivers;
- wrong inputs;
- wrong outputs;
- wrong errors;
- unresolved required captures.

This supports lifecycle and negative testing without changing the core runner.

## 13. Testing consequences

The executable interface creates three separate obligations.

### 13.1 Provider conformance

Run the real provider through `preverify()` and `postverify()`.

Question answered:

> Does the real provider satisfy the agreed interface?

### 13.2 Consumer contract testing

Run the consumer against `replay()`.

Question answered:

> Does the consumer behave correctly when given exactly the agreed interface?

### 13.3 Integration and certification

Connect the independently verified real provider and real consumers.

Question answered:

> Are the conforming components wired together correctly?

Integration should verify the connection rather than unnecessarily reproduce
all provider and consumer behavioural tests.

All implementation and certification remain subject to
[TEST_ADEQUACY.md](TEST_ADEQUACY.md).

## 14. Contract changes

A provider implementation failure does not invalidate consumer work merely
because provider code changes.

If the contract remains unchanged:

```text
provider fails -> fix provider -> verify same contract
```

Consumers remain valid against the same contract.

If the interface itself changes:

1. revise the contract explicitly;
2. identify every provider and consumer bound to it;
3. update affected scenarios;
4. revalidate affected implementations;
5. rerun integration/certification.

Contract evolution is visible work, not an inferred implementation side effect.

## 15. RepoWorkflow responsibility

RepoWorkflow represents and schedules the explicit graph.

It must not infer:

- whether an interface is stable;
- whether arbitrary changes are compatible;
- whether a consumer can ignore a changed contract;
- how provider and consumers should negotiate semantics.

Those decisions belong to the contract and its tickets.

RWF may later support mechanics such as locating contract artifacts, exposing
their ticket relationships, or running configured contract verification.
Those capabilities must consume an explicit contract rather than derive one
from implementation behaviour.

## 16. Initial implementation scope

A first implementation should support:

- deterministic scenario streams;
- free-function calls;
- member-function calls;
- symbolic object references;
- exact structured inputs and outputs;
- expected errors;
- captures and later references;
- provider `preverify()` and `postverify()`;
- consumer `replay()`;
- scenario completion validation;
- one reference language binding.

Initially defer:

- arbitrary predicates;
- automatic contract generation from provider behaviour;
- automatic compatibility inference;
- automatic interface discovery;
- unconstrained callbacks in contract scripts;
- claims of complete language neutrality.

## 17. Design invariants

1. One contract drives provider verification and consumer replay.
2. The contract is defined independently of provider implementation behaviour.
3. Calls are validated before real provider execution.
4. Provider outcomes are validated before a stream step commits.
5. Replay validates inputs before returning scripted outputs.
6. Stream order is deterministic.
7. The stream is immutable during one execution.
8. Symbolic references replace process-specific addresses in contracts.
9. Free/member wrappers share one comparison engine.
10. Language-specific semantics remain explicit when normalization is lossy.
11. Contract changes trigger explicit affected revalidation.
12. RWF schedules explicit contracts; it does not infer interface agreements.

## 18. Open design questions

Later specification must define:

- contract serialization format;
- value schema and comparison operators;
- binding-specific extension fields;
- error normalization;
- async/coroutine representation;
- object lifetime and aliasing;
- scenario composition and reuse;
- contract versioning and migration;
- how artifacts attach to tickets;
- integration scenario selection;
- whether an observe/record mode is useful for debugging.

Any observe/record mode must treat captured provider behaviour as untrusted
evidence.  It must never silently turn implementation behaviour into the
authoritative contract.

## 19. Decomposition and convergence

A speculative ticket grouping should separate contract semantics, comparison
runtime, provider verification, consumer replay, workflow state/scheduling,
integration, and certification where those are independently testable.

The predefined interface may be pre-existing or newly designed.  New design
work should attempt interface-first decomposition when it creates a coherent
boundary that allows useful overlap.

The interface used for decomposition or speculative execution is not
automatically the final production architecture.  After any related ticket
sequence or grouping converges, including a purely serial chain, review whether
to:

- retain the interface as a durable boundary;
- consolidate independently implemented pieces into one code path; or
- expose a higher-level interface that hides error-prone sequencing while
  retaining lower-level interfaces internally where justified.

The grouping does not need to have been identified as a Feature/Epic in
advance; a coherent feature/outcome may only become apparent after the
dependency path is decomposed.

Contract semantics must be frozen before provider and consumer runtime work is
treated as speculatively parallel-ready.  Final integration/certification must
exercise the resulting production design, not only the decomposition boundary.
