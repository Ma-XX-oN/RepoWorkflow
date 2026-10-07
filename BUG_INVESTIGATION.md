# Bug Investigation Protocol

Status: authoritative repository-neutral defect-investigation policy for
RepoWorkflow and every consumer project that uses RepoWorkflow.

This document defines how bugs are investigated before and during correction.
It complements [TEST_ADEQUACY.md](TEST_ADEQUACY.md), which owns verification
adequacy and closure requirements.

## 1. Required experiment cycle

Every bug investigation must maintain an explicit evidence log using repeated
cycles of:

```text
Problem
Hypothesis
Action
Learning
```

The cycle applies to every bug-resolution task.  The amount of detail may scale
with the complexity of the defect, but the four fields and evidence-driven
progression are required.

## 2. Problem

State the observed defect precisely.

Include enough objective evidence to distinguish the failure from an assumption,
for example:

- the exact failing command, test, or workflow;
- the relevant error/result;
- the candidate/revision being exercised;
- the minimum known conditions required to reproduce it.

Do not start from an unverified explanation of the symptom.

When practical, first turn the report into a deterministic failing test or
other repeatable objective reproduction.

## 3. Hypothesis

State one concrete explanation for the observed defect.

A useful hypothesis predicts something the next action can distinguish.  It
should identify a suspected mechanism, boundary, invariant violation, or state
transition rather than merely restating the symptom.

Prefer:

```text
The parser accepts this token because the variadic fallback is evaluated before
the static command alternative.
```

over:

```text
The parser is broken.
```

When several explanations remain plausible, test them separately rather than
silently combining them.

## 4. Action

Perform the smallest useful diagnostic or corrective action that tests the
current hypothesis.

Examples include:

- inspect the exact state consumed by the failing operation;
- add instrumentation at one disputed boundary;
- run one focused test with a controlled input change;
- compare a provider response with the authoritative contract;
- reduce a graph or state sequence while preserving the failure;
- make a narrowly scoped correction after the mechanism is established.

Do not make a broad implementation change merely to see whether the symptom
disappears.  If the action cannot distinguish the current hypothesis from
competing explanations, refine the experiment first.

## 5. Learning

Record what the action established before choosing the next step.

The Learning entry must say whether the hypothesis was:

- supported;
- disproved;
- narrowed;
- or still unresolved.

Also record any newly exposed fact that changes the next experiment.

Do not treat a changed symptom as proof of root cause without showing why the
action establishes that conclusion.

## 6. Repeat until the defect mechanism is known

Most non-trivial defects require more than one cycle:

```text
Problem
  ...

Hypothesis 1
  ...

Action 1
  ...

Learning 1
  ...

Hypothesis 2
  ...

Action 2
  ...

Learning 2
  ...
```

Continue until the evidence identifies the defect mechanism with sufficient
confidence to justify the fix.

A failed hypothesis is useful progress when its evidence rules out a plausible
cause.

## 7. Correction and confirmation

After the defect mechanism is established:

1. identify the violated requirement or invariant;
2. apply the smallest correction that restores that contract;
3. rerun the original reproduction;
4. verify the corrected observable behaviour;
5. run the relevant regression and interaction coverage;
6. retain a regression test where appropriate.

The detailed verification obligations are defined in
[TEST_ADEQUACY.md](TEST_ADEQUACY.md).

## 8. Escaped defects

When a bug escaped existing verification, investigate why the test system did
not expose it earlier.

Ask whether the escape reveals a reusable weakness such as:

- an omitted requirement;
- missing boundary or negative cases;
- an untested condition interaction;
- a shallow persisted-state assertion;
- a stale or unrealistic fixture;
- a missing assembled/public workflow;
- a missing platform/runtime case;
- a self-derived oracle;
- stale certification evidence.

Correct the reusable verification/process gap when it can recur elsewhere.
Fixing only the local product defect is incomplete in that case.

## 9. Preserve the log

Keep the experiment log with the durable work record for the bug, such as the
issue, pull request, or repository audit record.

The record should make it possible for a later worker to determine:

- what was observed;
- what explanations were tested;
- what each experiment established;
- why the selected fix follows from the evidence;
- what regression/prevention change was retained.

Do not rely on chat history as the sole record of a bug investigation.

## 10. Run-ending statement

When an investigation run stops before the bug is completely resolved, record
the immediate reason explicitly:

```text
Run ended because ...
```

Examples include a disproved hypothesis requiring a new experiment, a provider
dependency that cannot currently be exercised, or a newly discovered contract
decision requiring user input.

This statement does not replace the Learning entry.  It records why work
stopped at that point.
