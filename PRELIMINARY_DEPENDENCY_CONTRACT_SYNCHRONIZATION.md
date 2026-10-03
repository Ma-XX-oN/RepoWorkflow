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

For each direct dependency where consumer B depends on prerequisite A, verify:

1. A's postconditions satisfy B's relevant preconditions.
2. A's invariants are compatible with B's invariants.
3. B does not rely on a material guarantee from A that A never promises.

Carry established guarantees forward through the lane.  Do not treat each issue
as an isolated document.

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

## 6. Completion-time review

Reviewing known consumers before completing a prerequisite can remain a
defence-in-depth check, but it is not the primary prevention mechanism.

The primary synchronization pass occurs before implementation.

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
