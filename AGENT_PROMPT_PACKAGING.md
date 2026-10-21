# Coordinated Agent Prompt Packaging

Status: authoritative instructions for prompt handoff from a controller to
separately started workers.  Applies to RepoWorkflow-managed agent workstreams.

## 1. One PMD for shared instructions

`.pmd` means **Prompt Markdown**.  A controller produces **one shared PMD**
for the coordinated group of workers.  Its purpose is to avoid duplicating
common constraints, execution rules, dependency graph, ownership boundaries,
version checks, failure handling, evidence standards and handoff obligations.
Do **not** generate one PMD per worker when the workers share those policies.

Name the shared file using the **controller or coordinating ticket ID**:

```text
<repo-short-name>-#<ticket-id>-<description>.pmd
```

Examples:

```text
RWF-#699-manual-integration-workers.pmd
DC-#352-favicon-heartbeat-workers.pmd
```

Use the repository's established short name, the literal `#`, the exact
coordinating ticket number, and a concise hyphenated description.  Preserve
the `.pmd` extension; do not quietly substitute `.md`, issue-specific
copies or a legacy generic basename.  A new independent workstream gets
its own coordinating-ticket-named shared PMD, not one per leaf ticket.

Store the actual shared PMD in the user's ChatGPT **Library** where
`AGENT-CMD SPINUP` can read it.  Verify the exact Library file exists and
has the intended contents before issuing launch prompts.  A repository copy,
if kept for review, must be explicitly identified as a snapshot; it does not
replace the named Library attachment.

Keep the PMD generic **within the workstream**: it may contain its controller
ID, fixed children/dependency graph, source-of-truth requirements and the
common worker contract.  Each leaf ticket's distinct task, extra safeguards
and start-specific decisions belong in its **launch prompt** and in its
authoritative issue body, not in a duplicated PMD.

## 2. One independent fenced prompt per worker

For every worker the controller proposes to launch, write **one separate
fenced text block in the conversation**.  Do not put these copy/paste launch
prompts in GitHub issue bodies or issue comments.  Tickets record task
requirements, ownership, graph edges, acceptance tests and evidence links;
conversation prompts perform the actual worker handoff.

Each fence must be complete, independently copyable into a **new ChatGPT
conversation**, and have this exact structure:

1. The first line is a complete `AGENT-CMD SPINUP` command with the
   **same shared PMD filename** and all required quoted assignments.
2. Zero or more lines may follow with worker-specific instructions,
   prohibitions, MUST-observe rules, acceptance focus, or clarifications.
3. The **last line inside the fence** is the PMD basename prefixed with
   `@`.  It identifies the single shared Library file to attach/mount.
   Put nothing after that line within the fence.

Example for the controller of RWF #699:

```text
AGENT-CMD SPINUP RWF-#699-manual-integration-workers.pmd "issue"="700" "version"="V3"
MUST observe AUTONOMOUS_EXECUTION_WINDOW_RULE.
Implement RWF #700 only.  Preserve the controller and sibling ownership.
@RWF-#699-manual-integration-workers.pmd
```

Repeat the entire block for workers #701, #702 and #703 with the **same**
shared PMD filename and their own `"issue"="..." ` assignment and optional
worker-specific sentences.  Never ask a user to reconstruct a full launch
message by editing a combined multi-worker block.

The final `@...` line is **outside the command syntax**: it is the attachment
reference for the UI.  Ensure the actual matching Library file is selected
and mounted when pasting; a bare filename that is not accessible is not
proof that a receiving worker has read its instructions.  A receiving worker
must verify/read the exact attached file before executing.

## 3. Literal substitution and validation

The shared PMD may reference `$issue`, `$version`, or other explicitly
declared assignment names.  `AGENT-CMD` substitution is **literal**, not
recursive.  Every referenced variable must have a supplied value.  Keep
argument names stable and quote/escape the complete values so the receiving
worker can parse them without ambiguity.

When a file is unavailable, a variable is undefined, a version mismatches,
or an argument is malformed, report the **exact** defect; never invent
replacement values, claim ownership, or mutate the repository based on an
unexpanded or guessed prompt.

The `AGENT-CMD` line starts the receiving task; subsequent prompt lines
add worker-specific instructions subject to higher-priority project rules.
An issued command is **not** evidence of an agent having started.  Record
workers as unstarted until a separate conversation actually executes and
publishes an authorized ownership claim.

## 4. Controller checklist and correction policy

Before posting dispatch prompts:

- Verify the shared PMD's **ticket-prefixed filename**, Library existence,
  contents, version and allowed variable names.
- Verify all workers' current GitHub issue contracts, exact dependencies,
  unique edit ownership and parallel readiness.  Avoid stale graph snapshots.
- Check that each separate conversation fence starts with a full command,
  has matching literal `@PMD` as its **final** line, and supplies all args.
- Keep copy/paste **launch prompts only in the conversation**.  A ticket may
  link to this documentation, but must not become a substitute prompt queue.
- After a correction, explicitly supersede old prompts and old PMD names,
  so workers cannot accidentally execute two conflicting instruction sets.
- Do not merge branches, activate production, or claim an agent started
  just because its prompt was generated.  Track acceptance and handoffs.

This packaging contract complements, but does not override, issue ownership,
the autonomous execution window, the repository source-of-truth, or test and
approval gates in [WORK_GRAPH_SCHEDULING.md](WORK_GRAPH_SCHEDULING.md).
