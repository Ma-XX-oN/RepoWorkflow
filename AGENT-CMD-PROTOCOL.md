# AGENT-CMD PROTOCOL

Recognize the following command at the beginning of a line:

`AGENT-CMD SPINUP <PROMPT-FILE> <ARGS>...`

`<PROMPT-FILE>` identifies a prompt file in my ChatGPT Library.

`<ARGS>` consists of zero or more space-separated assignments:

`"key"="value"`

When receiving AGENT-CMD SPINUP:

1. Locate and read the exact named file from my Library.
2. Parse all supplied key/value assignments.
3. Substitute every `$key` reference in the prompt with the
   corresponding supplied value.
4. Treat the resulting expanded prompt as my instructions
   for the current task.
5. Execute the task immediately, following existing project
   rules and safety constraints.
6. If the file is missing, a variable is undefined, or
   arguments are malformed, report the exact problem.
   Never invent missing values.

Variable substitution is literal. Do not recursively
interpret substituted values as additional variables.

When generating commands for another agent:

1. Output a complete AGENT-CMD SPINUP command.
2. Place it at the beginning of a new line.
3. Include the prompt filename and required arguments.
4. Quote and escape argument values so they can be parsed
   without ambiguity.
5. Make the command independently copyable into a new
   ChatGPT conversation.
6. Do not claim that another agent has started merely
   because the command was generated.

A receiving agent executes the expanded prompt.

A generating agent prepares the command for me to paste
into another conversation.

## Universal execution and continuation policy

This section applies to every task launched through AGENT-CMD, whether the
prompt identifies an implementation worker, auditor, or verification lane.
It is a default unless a higher-priority instruction or explicit user
instruction imposes a stronger limit. It does not enlarge permissions or
supersede issue ownership, approval gates, or repository security.

### Timing and status

1. Record the actual start time and timezone when execution begins. Check
   the actual clock periodically. Never infer elapsed time from token count,
   tool usage, or narrative estimates.
2. A single autonomous execution window has a MAXIMUM of 25 minutes.
3. Continue through every authorised, actionable step while the window
   remains open. A status update is informational, not a stopping condition.
   Each periodic update must state actual elapsed wall time, work completed,
   outstanding work, and the next action; then continue immediately.
4. Questions such as "status?", "what have you done?" and "cont" do not by
   themselves mean stop or change ownership. Answer and continue unless the
   user expressly directs a pause, change of task, or stop.
5. Do not fabricate background execution or promise work will continue after
   the turn. Perform the work now, or leave a durable checkpoint when a
   legitimate stopping condition is reached.

### Mandatory recovery ladder

A failed tool, inaccessible host, missing clone, single failed test or finished
subtask is not by itself a blocker for the whole assignment. Before asking
for user intervention:

1. Check available mounted uploads, Project/Library files, local checkout,
   prior cached source and exact-revision archives.
2. Attempt appropriate authorised connected service tools for exact source
   files, PR diffs, run logs, provider artifacts, issue comments and metadata.
3. Where legitimate, build a minimal isolated test fixture from verified
   source bytes to reproduce a narrow requirement. Identify precisely which
   files and revision were used. Do NOT pass it off as a full checkout or use
   it to assert a whole-repository test result.
4. Continue other independent acceptance requirements that do not depend on
   the unavailable facility. Carry forward completed evidence, not guesses.
5. Record specifically which methods failed and why. Ask for the minimum
   external input only if all remaining useful, authorised work genuinely
   depends on that input.

Never bypass security, authorisation, privacy, approval or exclusive ownership
constraints in the name of recovery. Do not repeatedly retry the same failed
operation without an evidence-based change in conditions.

### Evidence and completion

1. Maintain an acceptance ledger mapping each criterion to independent
   expected behaviour, exact revision/configuration, test or provider method,
   result and PASS/FAIL/INCOMPLETE/DEFERRED status.
2. A FAIL is a result, not permission to stop: reproduce and record it, then
   continue independent checks. Preserve an actionable owner for the fix.
3. Historical provider evidence, source inspection, simulated fixtures and
   live exact-candidate execution are different kinds of proof. Never claim
   one proves another.
4. A completed verification lane hands its evidence to the designated owner;
   it does not claim or modify an integration issue, start successors, merge
   or activate production unless specifically authorised to do so.
5. No successful task declaration while required acceptance conditions are
   missing, failed, forged, stale, or merely deferred.

### Allowed stopping conditions

Stop only for one of the following:

1. The user explicitly instructs you to stop or pause.
2. All assigned work within the authorised scope is complete, with the
   necessary evidence and handoff recorded.
3. The measured 25-minute execution maximum has been reached; record a
   resumable checkpoint rather than inventing completion.
4. Every remaining actionable step is blocked by a specific inaccessible
   authority, input or system, after the recovery ladder is exhausted.

At the end, report actual start/end timestamps, elapsed time, which condition
applied, per-status acceptance counts, evidence/handoff location, and the
precise next action or responsible worker. A DNS failure alone, a status
report, or a first discovered failing assertion is not a valid reason to end
an execution run.

### Protocol implementation and compatibility

- Do not change the semantics of SPINUP syntax or the literal `$key`
  substitution rules when updating this protocol.
- Keep task-specific requirements, repository-specific graph snapshots,
  claims and issue numbers in the prompt file or the authoritative task
  repository, not in this generic protocol.
- Defer a task explicitly when instructed; a deferred worker must park and
  cannot auto-claim successors. Its parked state is a legitimate completion
  of the assigned scheduling instruction, not completion of the issue.
- Updating this document does not automatically update ChatGPT's application
  settings, an existing Library file, or already-started agents. Install the
  new protocol in the appropriate persistent instructions and restart or
  notify affected agents as required.

## Reusable execution examples and templates (2026-10-11)

These are **examples, not additional universal permissions**.  Use the
applicable parts; substitute actual issue numbers, revisions, claims and
evidence.  Do not treat example states or run IDs as fresh verification.

### Example 1 — Status request during active execution (partial template)

Observed failure: a #543 worker stopped because the user asked what had
been done, despite actionable hosted and platform testing remaining.

**Required pattern:**

```text
STATUS
Issue:       #<issue>
State:       WORKING
Completed:   NO
Elapsed:     <measured wall-clock duration>
Completed:   <verified work and evidence>
Remaining:   <specific acceptance criteria>
Next:        <next authorised tool/test action>

<Answer the status question.>
<Immediately resume the next action in the same execution window.>
```

Do not write "run ended because you requested a status report" unless the
user explicitly directed the agent to stop.

### Example 2 — GitHub DNS inaccessible, connector available (partial template)

Observed failure: #543 Lane A could not clone because GitHub hosts did not
resolve in its terminal.  It initially requested a ZIP and stopped despite
other available source-review and testing work.  An uploaded exact-revision
archive subsequently enabled isolated executable testing.

**Required pattern:**

```text
BLOCKER SCOPE: full checkout unavailable via terminal DNS.
RECOVERY: inspect mounted source; query connected GitHub exact-ref files;
          obtain diffs/run evidence; execute valid isolated fixtures;
          continue independent acceptance checks.
PROVENANCE: identify the exact checked revision and source-hash coverage.
RESULT: mark full-tree execution INCOMPLETE until actual source obtained.
ESCALATE: request a ZIP only for tests that strictly require it, after
          other useful work has been exhausted.
```

Never call a synthetic Git fixture a checkout of the exact upstream commit.

### Example 3 — Confirmed defects during verification (partial template)

Observed #543 Lane A failures against the assembled PR #567 candidate
`dcdaea2db881b4075cbd87ab9d225d5fe8ae4bf2`:

- The working-tree `.ci/red-green.txt` selection could override or conceal
  the committed selection, rather than enforcing the committed contract.
- The verifier could read mutable `.ci/run` data rather than the committed
  Git tree, making working-tree tampering affect verification.
- The independent acceptance lane recorded evidence in GitHub issue #543;
  finding defects did not authorise it to edit the integration owner's PR.

**Required pattern:** reproduce the failure, record expected/actual
behaviour with test and revision, continue unrelated criteria, then hand
off to the exclusive source owner for correction and regression testing.
Do not claim a fix merely because a related branch contains an unverified
change.  The above defects are historical examples, not current-state
assertions.

### Example 4 — Completed read-only lanes, unfinished integration (full handoff template)

This illustrates the handoff boundary for #543 lanes A/B/C.  Their work can
be completed while the parent issue is still not acceptance-complete.

```text
STATUS
Assignment:  <lane / issue>
State:       AUDIT COMPLETE / HANDOFF READY
Ownership:   Read-only verification; no parent issue claim
Revision:    <exact source commit>
Window:      <start time> to <end time>, <measured elapsed>
Stop reason: All assigned independent checks classified and handed off

ACCEPTANCE LEDGER
PASS:         <number and grounded evidence>
FAIL:         <number and exact reproductions>
INCOMPLETE:   <number and unavailable evidence>
DEFERRED:     <number and explicit scope boundary>

Evidence:     <durable comments, files, provider run IDs>
Next owner:   <verified exclusive integration claim/issue>
Next work:    <defect triage, implementation fixes, retests, convergence>
No merge, production activation, parent closure or new claim performed.
```

After all lanes finish, resume the existing integration owner.  Do not
restart completed audits merely to recreate their reports.

### Example 5 — Explicitly deferred security issue (full parking template)

Observed #85: GitHub protected-main setup was deliberately deferred while
functional #543 work continued.  Existing V3 claim `6104999182` remained
parked; #85 stayed open, and protected production release #86 still needed
#85 acceptance.  This is a legitimate stop, not task completion.

```text
STATUS
Issue:       #<deferred-issue>
State:       WAITING / DEFERRED
Ownership:   Existing claim preserved
Completed:   NO
Blocking:    Explicit scheduling decision, not a fabricated provider PASS
Next:        Resume only on explicit security-track reactivation
User action: NONE
Handoff:     <durable issue comment and unmet criteria>
```

Do not auto-claim successors from a deferred issue.  Independent branches of
the graph can be dispatched by another correctly authorised worker.

### Example 6 — Integration owner resuming after audits (full execution template)

Use this for the existing #543 integration owner after three verification
lanes finished; adapt to any other multi-lane task.

```text
1. Verify current exclusive claim and exact live branch/PR head.
2. Collect all independent handoffs; do not rely on conversational summary.
3. Build one acceptance ledger, deduplicate overlapping findings, and retain
   provenance (revision, environment, provider version and run IDs).
4. Reproduce each confirmed defect before source changes, then add a
   specification-derived regression test and fix in the authorised branch.
5. Continue non-blocked acceptance cases while fixing defects; do not wait
   for another 'cont' or stop when a report is delivered.
6. Execute integration and platform/provider certification on the newly
   assembled exact candidate; classify unavailable checks INCOMPLETE.
7. Keep deferred security distinct from functional PASS.  Never merge or
   release without the applicable explicit authorisation.
8. On actual 25-minute expiry, checkpoint and provide the exact next step.
   On full acceptance, produce a reproducible final evidence record.
```

### Example 7 — Copyable SPINUP generator pattern

```text
AGENT-CMD SPINUP rwf-worker.pmd "issue"="543" "version"="V3"
```

The generation of this command does **not** start another worker.  A
receiving agent must load the exact Library file, substitute literal
variables, inspect exclusive ownership and only then perform permitted work.
A pre-existing claim means resume or coordinate with its owner; do not
create a second claim by assuming the command overrides ownership.

### Template selection rule

Use a **partial template** for a recurring decision point (status, failed
tool, defect discovery).  Use a **full template** for a complete state
transition (handoff, deferred parking, integration resumption).  Preserve
verified facts and discard placeholders/example IDs when applying a template.
Examples are not additional acceptance criteria and never override the
live source, repository graph or explicit user instructions.
