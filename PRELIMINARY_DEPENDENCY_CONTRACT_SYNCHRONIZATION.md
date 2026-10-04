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

## 10. Third application: #187 implementation and integration

The #187 run applied the preliminary checks while implementing the semantic
transaction coordinator created by the second application.

The prerequisite review confirmed that #99, #100, and #101 supplied the
required lower-level state and concurrency guarantees.  The completion-time
consumer review then checked #187 directly against #64.  That comparison
confirmed that #64's multi-domain issue-start transition requires the
prepare/revalidate/commit/replay semantics implemented by #187; no additional
consumer-contract gap was found.

The run nevertheless exposed a separate integration drift.  While #187 was in
progress, main advanced through #189 and its repository version became 0.1.49.
The #187 branch still carried 0.1.48.  Merging the otherwise valid branch at
that point would therefore have regressed the repository version.

The branch was synchronized with current main and advanced to 0.1.50 before
integration.  Validation then passed on Linux, macOS, and Windows, and
post-merge validation and release also passed.

This observation is useful to the trial for two reasons:

1. the bounded prerequisite/direct-consumer checks remained useful without
   requiring recursive downstream design; and
2. dependency-contract compatibility alone is not sufficient at integration
   time.  Mutable repository-wide invariants can drift while parallel lanes are
   active and need a current-main integration check.

The version regression was not rejected by the existing CI before the manual
integration review found it.  Record this as a trial finding rather than an
authoritative new workflow rule for now.  Further runs should determine whether
the general requirement is a repository-wide invariant revalidation step, a
specific version-progression gate, or both.

No additional process rule is adopted from this single observation.  Continue
collecting comparable findings from subsequent runs before deciding how the
preliminary guidance and automated gates should change.



## 11. Fourth application: Lane A (#186 -> #185 -> #64 -> #142)

This trial applied the preliminary checks across a complete dependency lane rather
than one isolated issue.

The #186 prerequisite and direct-consumer checks found no additional contract
gap.  The frozen #189 environment contract mapped cleanly to canonical
`WriterIdentity` validation and remained sufficient for #185 and #64.

The #185 implementation exposed an ordering detail inside an otherwise complete
contract: identical relationship registration must be recognized as idempotent
before requiring an expected revision for conflicting replacement.  Requiring
the revision first would turn a harmless replay into a false conflict.  The
implementation and tests were corrected before integration.

The #64 pass required the #187 transaction contract to be applied to operations
whose materialization spans repository version, Git branch state, durable
lifecycle state, and worktree-local current-work state.  Because the transaction
record commits before materialization, each materialization step had to tolerate
replay after partial completion.  The resulting transition validates its
authoritative read set before commit and treats already-materialized compatible
state as success during replay.

The direct-consumer check from #64 to #142 found a concrete integration
constraint rather than a missing prerequisite: workspace creation cannot invent
a separate `rwf-workspace-N` branch/base and then reuse canonical issue-start
semantics without creating two branch models.  #142 therefore provisions the
registered canonical branch base and `issue-N` branch, invokes #64 in that
worktree, and publishes clone-local workspace state only after issue start
succeeds.

Two implementation failures were caught by full validation before integration:
a generated command-grammar edit contained literal newline escape text, and the
#142 test fixture initially emitted literal newline escape text into generated
files.  Both were construction errors rather than contract failures and were
corrected before merge.

The lane also strengthened the earlier integration-drift finding.  Parallel
workers repeatedly advanced `main` while lane branches were validating.
Several branches independently selected what was, at branch time, the next
stable repository version.  This produced repeated version collisions and
repair commits (#196 and #201).  #64's post-merge validation itself passed, but
its release job correctly refused publication because its checked-out commit
was no longer authoritative `main` by the time release ran.  A later
authoritative main commit carried the same version forward.

This is stronger evidence that stable-version selection/publication is a
concurrency problem, not merely a stale-branch check.  A current-main check
before merge reduces one failure mode but cannot reserve a version against
another lane that advances concurrently.  Continue treating this as a trial
finding until the collected runs are evaluated; do not yet freeze a replacement
version-allocation protocol from this observation alone.
