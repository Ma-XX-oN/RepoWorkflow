# Preliminary Dependency Contract Synchronization

Status: preliminary trial guidance.  This is not yet an authoritative RWF
workflow contract.

Tracking issue: #163.

## 1. Purpose

RWF dependency edges can be structurally correct while a prerequisite's stated
scope is still insufficient for a known consumer.  This trial is intended to
find those mismatches before implementation rather than when the consumer is
already being built.

The method should remain cheaper than implementation.  It is not a requirement
to design or mock every downstream issue in advance.

## 2. Normal verification pass

Before implementing a dependency lane, traverse from ready leaves toward the
root.

For each direct dependency where consumer B depends on prerequisite A, verify
the dependency edge using this trial matrix:

| Check | Question |
| --- | --- |
| Contract | Do A's postconditions satisfy B's relevant preconditions, and are their invariants compatible? |
| Capability | Is there an executable production operation that supplies the guarantee, rather than only a schema, store, reader, or interface? |
| Provenance | Does every required input have a legitimate source, validation point, and path to the consumer? |
| Authority | Is the authoritative source of each required fact unambiguous? |
| Transaction | Are mutations that must succeed or fail together covered by the required atomicity and recovery boundary? |
| Failure | Can failure appear as success or leave authoritative partial state? |
| Invocation | Is there a real production path from B to the capability A is assumed to supply? |

Carry established guarantees forward through the lane.  Do not treat each issue
as an isolated document.

An artifact existing is not sufficient evidence that a capability exists.  For
a required postcondition, identify the production operation that can actually
make it true.

For fan-out, verify the prerequisite against each direct consumer.  For fan-in,
verify that guarantees supplied by independent prerequisites are mutually
compatible at the consumer.

## 3. Escalation

Stop when the declared contracts are clearly compatible.

If comparison exposes an ambiguity or apparent gap, perform only enough
interface mock-up or dry-run analysis to answer how the consumer would use the
prerequisite and what guarantee is missing.

Do not partially implement the consumer merely to validate planning.

The intended progression is:

```text
contract comparison
        |
        +-- clearly compatible --> stop
        |
        +-- ambiguity/gap
                |
                v
        lightweight interface dry-run
                |
                +-- sufficient --> stop
                |
                +-- missing guarantee --> revise decomposition/specification
```

## 4. Graph changes

After an initial lane passes, revalidate affected paths toward the root when an
issue contract or relationship changes.

Do not repeat a full graph review for an isolated change unless the change
alters broad decomposition assumptions.

## 5. Implementation discoveries

Not every later discovery is a planning failure.

Classify a missing prerequisite as:

- a planning miss when it was reasonably derivable from already-known consumer
  contracts; or
- an implementation discovery when it depended on experimentation, platform
  behaviour, or information that was not reasonably available during planning.

When a completed prerequisite is genuinely insufficient, create an explicit
repair issue rather than hiding prerequisite repair inside the consumer.

## 6. Completion-time direct-consumer review

The primary synchronization pass still occurs before implementation.

Before completing prerequisite A, also inspect each known direct consumer B and
apply the same matrix only to the A -> B edge.  Ask whether A provides the
capability B believes it provides.

This is deliberately bounded.  Do not recursively design B's consumers or
mock-implement the downstream graph.  For A -> B -> C, completing A requires
checking B's expectations of A, not designing C.

This completion-time pass is both defence in depth and an opportunity to catch
a missing production boundary while the producer's implementation details are
still fresh.

## 7. Trial evaluation

After several applications, assess:

- prerequisite gaps found before implementation;
- false alarms or unnecessary analysis;
- gaps that still escaped into implementation;
- planning time and complexity added;
- whether escalation stayed appropriately limited; and
- whether this guidance should be revised, adopted as authoritative, or
  dropped.

## 8. First application: workspace readiness lane

The first pass examined the current relationship/readiness lane:

```text
#77 + #101 -> #145 relationship store/reader
#141 + #145 -> #144 workspace readiness
```

The pass found a missing prerequisite before #144 implementation.

`WORKSPACE_READINESS.md` requires readiness to use both canonical direct
relationships and current durable issue lifecycle state.  #145 deliberately
provides relationship state only.  #79 defines lifecycle records, but the graph
had no leaf implementing the canonical durable lifecycle store/reader needed by
#144.

Issue #164 was therefore created to implement that boundary.  #144 now directly
depends on #164 as well as #141 and #145.

The same missing boundary was visible in existing consumers #64, #98, and #72,
which write or project durable lifecycle facts.  Their prerequisite lists were
updated to include #164.

This is exactly the class of error the trial is intended to prevent: the generic
state-store prerequisite (#101) existed, but the semantic lifecycle layer
required by downstream consumers had not been represented as an implementation
issue.


## 9. Second application: issue-start convergence

The next pass examined the convergence into canonical issue start:

```text
#120 + #118 + existing state/relationship prerequisites -> #64 -> #142
```

The expanded matrix found three missing production boundaries before #64
implementation.

First, #145 supplied canonical relationship storage and readback, but no
production operation populated the graph.  #64 requires explicit umbrella,
dependency, branch-base, and integration-target facts to be recorded and is
forbidden from manufacturing them from ticket prose or Git ancestry.  #185 was
created for the missing canonical relationship-registration transition.

Second, durable stores require the writer/session identity defined by #99, but
the production command path had no legitimate provenance for that input.
#186 was created to provide explicit validated runtime writer/session identity.
Applying the revised provenance check also showed that #185 itself consumes
#186; that dependency must be represented explicitly rather than discovered
again during #185 implementation.

Third, #64 changes several authoritative state domains as one semantic
transition.  #101 supplies single-record compare-and-swap, while #99 requires a
recoverable protocol when an invariant spans records or domains that cannot be
published atomically.  #187 was created for that missing transaction
coordinator.

These findings refine the trial in three ways:

1. verify executable production capabilities rather than treating supporting
   artifacts as equivalent to operations;
2. trace every required input from authoritative origin through validation to
   its consumer; and
3. identify the full mutation set for a semantic transition and verify that its
   atomicity/recovery boundary covers that set.

The pass remains intentionally shallow: it verifies direct dependency edges and
escalates only when an edge exposes a concrete ambiguity or missing guarantee.
