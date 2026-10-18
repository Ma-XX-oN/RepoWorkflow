# PMD Authoring Specification

Status: authoritative guidance for authoring task-specific AGENT-CMD prompt files.
See [AGENT-CMD-PROTOCOL.md](AGENT-CMD-PROTOCOL.md) for the separate,
task-neutral command parser, substitution, execution, recovery and safety rules.

## 1. Purpose and boundaries

A \`.pmd\` is a reusable, human-readable prompt for a particular family of
tasks.  It avoids repeating large instructions whenever another worker needs
the same workflow.  It is not intrinsically a GitHub ticket worker: future PMDs
may describe audits, research, maintenance, verification or other assignments.

The AGENT-CMD protocol defines **how** to load, expand and execute a prompt.
Each PMD defines **what** that particular worker must do and which concrete
inputs, dependencies and acceptance results govern that work.

Version-controlled PMDs and their authoring rules may live in a repository,
such as RepoWorkflow or a consumer repository.  The current AGENT-CMD command
still loads a named PMD from ChatGPT Library at execution time.  Committing a
file to Git does not automatically install or update that Library copy, nor
does updating a Library copy change Git.  Confirm the intended runtime copy
is attached before relying on it.

## 2. Minimum required version contract

Every authored PMD MUST:

1. Declare its **exact filename** and a **literal prompt version**, e.g.,
   \`Prompt filename: example-worker.pmd\` and \`Prompt version: V2\`.
2. Declare which SPINUP arguments it expects, including \`"version"\`.
3. Compare the literal supplied \`$version\` to the declared prompt version
   immediately after expansion, **before any claim, mutation or execution**.
4. Stop clearly on mismatch, naming both expected and supplied versions.
5. Increment the declared prompt version when revised instructions are
   released for workers to use.  Commands for that revision use the new value.

Example error:

\`\`\`text
STOP: PROMPT VERSION MISMATCH
Expected PMD revision: V2
Command supplied: V1
No claim or repository changes made.
\`\`\`

The version is a **wrong-prompt guard only**.  It is NOT a ticket-claim ID,
agent identity, ownership namespace, execution mode, authority to replace an
owner, repository semantic version or CI candidate version.

No checksum, separate \`START/RESUME/TRANSFER\` syntax or independent revision
service is required.  The PMD's literal version declaration and supplied
\`"version"\` argument are sufficient for this contract.  If a command and
wrong file happen to declare the same revision, this check alone cannot detect
that error; the exact filename check remains independently required.

An existing issue claim stays valid when a PMD advances from V1 to V2.
A worker resuming under V2 must find and respect the existing claim/session.
A different worker may take over only on explicit operator authorisation
and after verifying the actual claim and recording an auditable transfer.
**A PMD revision alone never releases or supersedes ownership.**

## 3. Task-specific content

After the minimum version declaration, document only what the task needs.
The following fields are a recommended checklist, not a mandatory form for
all future kinds of PMD:

- **Purpose and role:** outcome, audience, repositories/services and limits.
- **Arguments:** names, required values, allowed ranges and exact mapping.
- **Authority:** task-specific permissions, forbidden mutations, handoffs,
  approvals and where the authoritative specification lives.
- **Inputs and prerequisites:** files, exact branches or revision identities,
  interfaces, credentials/permissions boundaries and readiness conditions.
- **Execution procedure:** concrete steps, dependencies and safe recovery.
- **Acceptance:** required observable behaviour, negative cases, evidence
  types, output artifacts, independent verification and completion criteria.
- **Handoff/output:** durable findings, checkpoint location, next action and
  whether successors may be proposed or launched.

Avoid copying the universal 25-minute execution window, continuation ladder,
status policy or approval protections into every PMD.  Cite the AGENT-CMD
protocol and add only stricter, genuinely task-specific instructions where
necessary.  A PMD must not override higher-priority instructions or the
current ticket's authoritative acceptance requirements.

A PMD can include placeholders such as \`$issue\`, \`$version\`, or
\`$target\`.  Every referenced variable must be supplied, and substitution is
literal and nonrecursive.  Do not invent absent values, re-expand substituted
text or change AGENT-CMD quoting/escaping semantics.

## 4. Ticket-completion workers (current use)

For an issue/ticket worker, include these additional specifications:

1. **Qualified ticket mapping:** an explicit issue-to-repository mapping.
   Never guess the repo from an unqualified number.
2. **Direct dependency graph:** real prerequisite edges, independent ready
   leaves, convergence/join owners and intentionally deferred work.
   Distinguish *claim eligibility* from *final integration acceptance* when
   preparatory work may proceed independently.
3. **Ownership boundaries:** existing claims, owner sessions, branch names,
   shared files, exclusive mutation surfaces and required coordination.
   Examine live issue comments/branch/PR evidence before any new claim.
4. **Acceptance per ticket:** concrete contract, tests (including RED/GREEN
   and negative cases), expected behaviour, exact candidate, failure handling
   and evidence/handoff location.  Synthetic and browser/provider evidence
   are different; passing CI for an older SHA is not current certification.
5. **Work and recovery:** apply the general protocol and live repository
   requirements; complete authorised independent steps after any failure.
   Record PASS/FAIL/INCOMPLETE/DEFERRED against each acceptance criterion.
6. **Completion and successor policy:** close only when the assigned ticket
   meets its actual acceptance; do not call an integration group done merely
   because leaves passed.  Honour every owner/merge/production approval gate.
7. **Resume and handoff:** preserve an existing claim when a worker resumes
   from a checkpoint, even with a newer PMD.  Explicit takeover instructions
   require verification and audit rather than a new revision-based claim.

A frozen graph is a scheduling snapshot, **not** authority to contradict a
newer explicit issue or user decision.  When sources conflict, surface the
specific inconsistency and update the authoritative graph deliberately.

RepoWorkflow's [WORK_GRAPH_METHODOLOGY.md](WORK_GRAPH_METHODOLOGY.md),
[RELATIONSHIP_GRAPH.md](RELATIONSHIP_GRAPH.md) and
[PARENT_BRANCH_WORKFLOW.md](PARENT_BRANCH_WORKFLOW.md) remain authoritative
for their respective graph, relationship and branch invariants.  This PMD
authoring guide does not redefine them.

## 5. Command-generation convention

When preparing a command for another ChatGPT conversation, output one
independently copyable complete SPINUP invocation for **each** worker.  The
filename in the command and final attachment line must match the authored
PMD exactly.  Put the \`@filename.pmd\` mention on the **last separate line**
of each command block:

\`\`\`text
AGENT-CMD SPINUP example-worker.pmd "issue"="123" "version"="V2"
@example-worker.pmd
\`\`\`

The person launching the worker must select the actual attachment in the
ChatGPT \`@\` picker if plain text does not resolve it.  Printing a command
does not launch any worker or transfer a ticket claim.  The receiving worker
must still inspect live prerequisites, claims and the prompt revision.

For tasks without tickets, use appropriate task-specific arguments instead
of inventing an issue or forcing an artificial dependency graph.

## 6. Safe revision procedure

1. Read the authoritative prompt and affected live task contracts.
2. Make the required task-specific changes, increment the literal prompt
   version, and update example SPINUP commands to match.
3. Verify the declared filename, all argument references, wrong-version
   stopping behaviour, current task facts, links and successor mapping.
4. Preserve already-active claim/session identities.  Specify any explicit
   owner transfer separately; do not infer a new claim namespace from V2.
5. Commit the authored PMD in its appropriate repository when version control
   is desired.  If agents load it from Library, update the Library copy
   separately and verify that copy before dispatching workers.
6. Existing worker conversations do not automatically reload the changed PMD.
   Resume/notify them explicitly when they need the new instructions.

## 7. Review checklist

- Is the declared PMD filename correct and the literal version unambiguous?
- Does a mismatched supplied \`$version\` stop **before** any mutation?
- Does a new version preserve all existing ticket claims by default?
- Is scope task-specific and free of duplicated generic protocol machinery?
- Are required arguments, acceptance results and ownership boundaries clear?
- Are issue numbers repository-qualified and graph edges direct, if relevant?
- Are external/browser evidence and integration owners distinguished?
- Does each generated command end with its exact \`@filename.pmd\` line?
- Are repository and Library copies clearly distinguished and verified?
- Have security, merge and production approvals been preserved?
