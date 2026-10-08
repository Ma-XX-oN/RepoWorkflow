# Executable Interface Contract Proposal

Status: proposal for repository-neutral interface-first decomposition,
deterministic contract verification, replay, and cross-language bindings.

This proposal extends the interface-oriented decomposition already described by
[WORK_GRAPH_METHODOLOGY.md](WORK_GRAPH_METHODOLOGY.md) and
[WORK_GRAPH_TESTING.md](WORK_GRAPH_TESTING.md).  It does not replace either
document while this proposal remains non-authoritative.

## 1. Purpose

Some dependency chains exist only because a provider implementation and a
consumer implementation need to agree on an interface.

For example:

```text
grammar -+- implement tab completion
         |
         +- implement some other feature
```

The consumer does not fundamentally need the completed provider
implementation.  It needs an agreed interface that the provider promises to
implement.

If that interface is extracted first, the graph becomes:

```text
                  interface contract
                  /       |       \
                 /        |        \
       grammar provider  completion  other consumer
                 \        |        /
                  \       |       /
                   integration/certification
```

Provider and consumer work can then proceed in parallel.  Each side can also be
tested independently against the same executable contract.

The central principle is:

> A provider and every consumer agree on an explicit interface before parallel
> implementation begins.  Provider and consumer tests execute the same
> deterministic interface contract from opposite sides.

## 2. The interface contract is a first-class work product

RepoWorkflow must not infer whether two tickets have a stable enough interface
for parallel work.

The tickets define that agreement.

A contract ticket specifies the observable boundary between a provider and its
consumers.  Once that contract is accepted:

- the provider ticket implements the contract;
- consumer tickets may implement against the contract immediately;
- provider and consumer tickets are parallel-ready;
- integration waits for both sides;
- provider implementation failures do not invalidate consumers when the
  contract remains unchanged;
- changing the contract is an explicit contract revision that requires affected
  consumers to be revalidated.

For the grammar/completion example, the contract must specify the information
that completion receives from the object representing the current CLI parse.
The contract must be precise enough for completion to be implemented and tested
without the real parser implementation.

## 3. Executable rather than prose-only

The interface must be scriptable.

A prose contract remains useful for rationale, ownership, and explanation, but
the observable call behaviour should also have a deterministic executable
representation.

A contract scenario describes an ordered stream of expected events such as:

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

The contract script must not depend on the provider implementation.

## 4. Comparing stream

The runtime is centred on a comparing stream.

```text
InterfaceContract
      |
      v
ComparingStream
      |
      v
InterfaceRunner
```

The stream is the single ordered source of truth for provider verification and
consumer replay.

The stream is immutable during execution.  Runtime state consists of the
current position, captured symbolic values, and any currently in-flight call.

A failure should identify the exact stream event that failed, for example:

```text
expected event 17:
  member: $parser.valid_next
  args:   ["4"]

observed:
  member: $parser.current_node
  args:   []
```

This is preferable to a generic mock failure because the error identifies the
contract boundary and exact divergence.

## 5. Provider verification

A provider implementation is verified by executing real calls through the
contract runner.

The provider-side lifecycle is:

```text
preverify(...)
real call
postverify(...)
```

A forwarding helper may provide the ordinary integration point:

```text
fwd(...)
  -> preverify(...)
  -> invoke real function/member
  -> postverify(...)
  -> return the real result
```

The wrapper must not alter successful provider behaviour.

### 5.1 preverify

`preverify()` validates the call before provider code executes.

It verifies at least:

- the next expected stream event;
- free-function or member-function identity;
- symbolic receiver identity for member calls;
- argument count;
- argument values;
- captured references;
- ordering;
- deterministic preconditions represented by the contract.

An unexpected call must fail before the underlying provider function is
invoked.

`preverify()` does not commit the stream event as completed.  It establishes
the in-flight call that `postverify()` must complete.

### 5.2 postverify

`postverify()` validates the provider outcome.

It verifies at least:

- expected returned value;
- expected structured output;
- expected error or exception;
- symbolic captures produced by the call;
- deterministic postconditions represented by the scenario.

Only successful `postverify()` advances the stream past the call.

If provider execution produces an unexpected exception or return value, the
runner reports the mismatch without silently advancing the contract.

## 6. Consumer replay

Consumers use the same contract without the provider implementation.

`replay()` performs the consumer-side operation:

```text
consumer call
    |
    v
replay(...)
    |
    +-- validate function/member identity
    +-- validate receiver when applicable
    +-- validate inputs
    +-- retrieve scripted output/error
    +-- apply captures
    +-- advance the stream
    |
    v
consumer receives scripted result
```

Replay outputs come from the contract.  They are not generated by arbitrary
callbacks or copied from current provider behaviour.

This permits a consumer ticket to implement and test its complete behaviour
while the provider ticket is still being implemented.

Provider verification and consumer replay must use the same input comparison,
capture, sequencing, and output semantics.

## 7. Shared runtime primitives

The public operations should share one comparison engine rather than implement
three interpretations of the contract.

Conceptually, the common primitives include:

```text
match_event()
match_receiver()
match_inputs()
match_output()
match_error()
capture_value()
resolve_reference()
advance()
finish_scenario()
```

Then:

```text
preverify()
  = match event + receiver + inputs

postverify()
  = match output/error + capture + advance

replay()
  = match event + receiver + inputs
    + obtain scripted output/error
    + capture + advance
```

The exact implementation language and names are not fixed by this proposal.

## 8. Free functions and member functions

The runner should provide distinct front ends for free functions and member
functions while sharing the same comparing-stream implementation.

A free-function call is identified by:

```text
function + arguments
```

A member-function call is identified by:

```text
receiver + member + arguments
```

The member-function interface therefore receives an object/receiver
unconditionally.

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

Both are thin adapters over one shared contract executor.

## 9. Symbolic object identity

Contract scripts must not depend on process-specific object addresses.

A member object should be assigned a symbolic identity such as:

```text
$parser
$repo
$session
```

A call may capture a real object under that symbolic identity:

```text
create_parser(...) -> $parser
$parser.parse(...)
$parser.valid_next(...)
```

In provider-verification mode, the runner maps the real runtime object to the
symbolic identity.

In replay mode, the runner supplies a replay-side representative associated
with the same symbolic identity.

Object identity, lifetime, and aliasing semantics remain binding-specific where
the common model is insufficient.

## 10. Value and error model

The common contract format should support a small deterministic set of
portable-enough value forms, including:

- null/no-value;
- booleans;
- integers;
- floating-point values with defined comparison semantics;
- strings;
- ordered sequences;
- mappings/structured records;
- symbolic references;
- deterministic typed errors.

The common model is intentionally not described as fully language-neutral.
Language neutrality is only an approximation.

Different runtimes expose different semantics for:

- object identity and lifetime;
- integer width and overflow;
- references versus values;
- ownership and borrowing;
- mutation and aliasing;
- exceptions, error codes, and result objects;
- async execution;
- dispatch and overload resolution.

The design goal is therefore:

> A common deterministic contract model with explicit per-language bindings and
> extensions for semantics that cannot be faithfully normalized.

Bindings must not hide semantic differences merely to claim portability.

## 11. Determinism

Contract scripts must be wholly deterministic.

The core contract language must not permit arbitrary user code or arbitrary
predicates to decide whether a call matches.

Prefer declarative matching operations such as:

- exact scalar equality;
- exact ordered sequence equality;
- exact mapping equality;
- selected structured-field matching;
- type/category constraints where defined;
- symbolic-reference identity;
- explicit deterministic numeric constraints;
- explicit expected errors.

If richer matching becomes necessary, it should be added as a named,
specified, deterministic contract operation rather than as embedded host
language code.

## 12. Scenario lifecycle

An interface normally requires more than one case.

A contract therefore contains named deterministic scenarios, for example:

```text
ordinary completion
empty completion
dynamic grammar completion
invalid token
provider error
repeated operation
changed parser state
```

Each scenario has an independent comparing stream and must finish with no
unconsumed required events.

Scenario completion should detect:

- missing expected calls;
- extra calls;
- wrong call order;
- wrong receivers;
- wrong inputs;
- wrong outputs;
- wrong errors;
- unresolved required captures.

## 13. Work-graph decomposition

The interface contract changes the correct dependency graph.

Do not model:

```text
provider implementation
        |
        v
consumer implementation
```

when the consumer only requires an agreed interface.

Model:

```text
                  interface contract
                  /              \
                 v                v
       provider implementation  consumer implementation
                 \              /
                  v            v
               integration/certification
```

With multiple consumers:

```text
                      contract
                 /       |       \
                v        v        v
             provider consumer1 consumer2
                \        |       /
                 \       |      /
                  integration
```

This is ordinary parallel execution after the contract ticket completes.  RWF
does not need speculative scheduling to create the parallelism.

## 14. Testing consequences

The executable contract creates three distinct test obligations.

### 14.1 Provider conformance

Run the real provider through `preverify()` and `postverify()`.

Question answered:

> Does the real provider satisfy the agreed interface?

### 14.2 Consumer contract testing

Run the consumer against `replay()`.

Question answered:

> Does the consumer behave correctly when given exactly the agreed interface?

### 14.3 Integration and certification

Connect the real provider and real consumer after both independently conform.

Question answered:

> Are the independently verified components wired together correctly?

Integration testing should not unnecessarily reproduce every provider and
consumer behavioural test.  Its primary responsibility is the real connection
between already-verified sides.

All implementation and certification remain subject to
[TEST_ADEQUACY.md](TEST_ADEQUACY.md).

## 15. Contract changes

A provider test failure does not invalidate consumer work merely because the
provider implementation changes.

If the agreed interface remains unchanged:

```text
provider fails
    |
    v
fix provider
    |
    v
verify same contract
```

Consumers remain valid against the same contract.

If the interface itself must change:

1. revise the contract explicitly;
2. identify every provider and consumer bound to that contract;
3. update their replay/conformance scenarios as required;
4. revalidate affected implementations;
5. rerun integration/certification.

Contract evolution is therefore visible work rather than an inferred side
effect of provider implementation.

## 16. Relationship to RepoWorkflow

RepoWorkflow's role is to represent and schedule the explicit work graph.

It must not infer:

- whether an interface is stable;
- whether arbitrary implementation changes are compatible;
- whether a consumer can safely ignore a changed contract;
- how two teams should negotiate interface semantics.

Those decisions belong to the contract and its tickets.

RepoWorkflow may later support the mechanics around executable contracts, such
as locating contract artifacts, exposing their ticket relationships, or
running configured verification commands.  Such capabilities must consume the
explicit contract rather than derive one from implementation behaviour.

## 17. Initial scope

A first implementation should remain deliberately small.

It should support:

- deterministic scenario streams;
- free-function calls;
- member-function calls;
- symbolic object references;
- exact structured inputs and outputs;
- expected errors;
- captures and later references;
- provider `preverify()` / `postverify()`;
- consumer `replay()`;
- scenario completion validation;
- one language binding implemented as the reference binding.

It should defer until separately specified:

- arbitrary predicates;
- automatic contract generation from provider behaviour;
- automatic compatibility inference;
- automatic interface discovery;
- unconstrained host-language callbacks inside contract scripts;
- claims of complete language neutrality.

## 18. Design invariants

The proposal depends on the following invariants:

1. One contract representation drives provider verification and consumer replay.
2. The contract is defined independently of provider implementation behaviour.
3. Calls are validated before real provider execution.
4. Provider results or errors are validated before a stream step commits.
5. Replay validates consumer inputs before returning scripted outputs.
6. Stream order is deterministic.
7. The stream is immutable during one execution.
8. Symbolic references replace process-specific object addresses in contracts.
9. Free/member wrappers share one comparison engine.
10. Language-specific semantics remain explicit when normalization is lossy.
11. Contract changes are explicit work and trigger affected revalidation.
12. RWF schedules explicit contracts; it does not infer interface agreements.

## 19. Open design questions

The following details require later specification:

- exact contract serialization format;
- exact value-schema and comparison operators;
- representation of binding-specific extension fields;
- error normalization rules;
- async/coroutine representation;
- object lifetime and aliasing rules;
- scenario composition/reuse;
- contract versioning and migration;
- how contract artifacts attach to tickets;
- how integration tests select and execute scenarios;
- whether an observe/record mode is useful for debugging without granting the
  observed behaviour contract authority.

Any observe/record capability must treat captured provider behaviour as
untrusted evidence.  It must never silently convert implementation behaviour
into the authoritative contract.

## 20. Proposed next decomposition

A future implementation epic should separate at least:

1. contract/script semantics;
2. comparing-stream model;
3. core comparison and capture engine;
4. free-function binding;
5. member-function binding;
6. provider verification lifecycle;
7. consumer replay lifecycle;
8. reference language binding;
9. provider/consumer/integration certification;
10. work-graph methodology integration.

The contract semantics must be frozen before provider and consumer runtime
implementations are treated as parallel-ready.
