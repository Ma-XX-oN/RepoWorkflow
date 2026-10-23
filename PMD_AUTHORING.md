# PMD Authoring Specification

Status: authoritative guidance for task-specific AGENT-CMD prompt files.
See [AGENT-CMD-PROTOCOL.md](AGENT-CMD-PROTOCOL.md) for the separate,
task-neutral command parser, substitution, execution, recovery and safety rules.

## 1. Purpose and boundaries

A `.pmd` is a reusable, human-readable prompt for a particular family of
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
   `Prompt filename: example-worker.pmd` and `Prompt version: V2`.
2. Declare which SPINUP arguments it expects, including `"version"`.
3. Compare the literal supplied `$version` to the declared prompt version
   immediately after expansion, **before any claim, mutation or execution**.
4. Stop clearly on mismatch, naming both expected and supplied versions.
5. Increment the declared prompt version when revised instructions are
   released for workers to use.  Commands for that revision use the new value.

Example error:

```text
STOP: PROMPT VERSION MISMATCH
Expected PMD revision: V2
Command supplied: V1
No claim or repository changes made.
```

The version is a **wrong-prompt guard only**.  It is NOT a ticket-claim ID,
agent identity, ownership namespace, execution mode, authority to replace an
owner, repository semantic version or CI candidate version.

No checksum, separate `START/RESUME/TRANSFER` syntax or independent revision
service is required.  The PMD's literal version declaration and supplied
`"version"` argument are sufficient for this contract.  If a command and
wrong file happen to declare the same revision, this check alone cannot detect
that error; the exact filename check remains independently required.

An existing issue claim stays valid when a PMD advances from V1 to V2.
A worker resuming under V2 must find and respect the existing claim/session.
A different worker may take over only on explicit operator authorisation
and after verifying the actual claim and recording an auditable transfer.
**A PMD revision alone never releases or supersedes ownership.**

### Worked example: revising a prompt without changing its ticket claim

First, an author publishes `example-ticket-worker.pmd` at `V1`:

```text
# example-ticket-worker.pmd (initial revision)
Prompt filename: example-ticket-worker.pmd
Prompt version: V1
Required arguments: "issue", "version"
Before work: verify supplied $version equals V1; otherwise STOP.
Task: implement the accepted requirements of example/Repo #$issue.
```

The operator launches it with:

```text
AGENT-CMD SPINUP example-ticket-worker.pmd "issue"="101" "version"="V1"
@example-ticket-worker.pmd
```

Later, the author improves the instructions.  The new PMD declares `V2`
and validates against `V2` instead of `V1`.  The filename and the
repository's existing ticket claim are unchanged:

```text
# example-ticket-worker.pmd (revised excerpt)
Prompt filename: example-ticket-worker.pmd
Prompt version: V2
Required arguments: "issue", "version"
Before work: verify supplied $version equals V2; otherwise STOP.
Task: implement the clarified requirements of example/Repo #$issue.
```

The revised launch command is:

```text
AGENT-CMD SPINUP example-ticket-worker.pmd "issue"="101" "version"="V2"
@example-ticket-worker.pmd
```

If the `V2` file is attached to the **old V1 command**, execution stops:

```text
STOP: PROMPT VERSION MISMATCH
Expected PMD revision: V2
Command supplied: V1
No claim or repository changes made.
```

If `example/Repo #101` was claimed under V1, its recorded claim and
session **remain valid** under V2.  Resuming that work means verifying and
continuing the existing claim, not creating another claim.  A new agent
requires an **explicit takeover instruction** and verified handoff.

These examples use fictional issues; they are not instructions to claim
tickets in any real repository.

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

A PMD can include placeholders such as `$issue`, `$version`, or
`$target`.  Every referenced variable must be supplied, and substitution is
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

### Worked example: two parallel tickets and one convergence ticket

Suppose the authoritative ticket graph for fictional `example/Recorder` is:

```text
example/Recorder #101 (capture contract)  ---+
                                             +--> #103 (integration)
example/Recorder #102 (writer contract)   ---+
```

A dedicated PMD for that family of work could contain this **excerpt**:

```text
# recorder-ticket-worker.pmd
Prompt filename: recorder-ticket-worker.pmd
Prompt version: V2
Required arguments: "issue", "version"
Before ANY claim: require supplied $version == V2; otherwise STOP.

Repository: example/Recorder
Allowed issues: 101, 102, 103
Direct prerequisites:
  #101: none
  #102: none
  #103: #101 and #102 independently accepted

On start: read live issue, comments, branch, PR and claim history.
  Verify the selected ticket is eligible and unclaimed, or that an
  explicit resume/takeover instruction authorizes an existing claim.
  Preserve owner and worktree boundaries; never infer a new owner
  from the PMD version.

Ticket-specific deliverables:
  #101: capture contract and tests; exact source and CI evidence.
  #102: writer contract and tests; exact source and CI evidence.
  #103: independently test assembled #101 + #102 integration.

On failure: preserve a precise acceptance ledger and resume checkpoint.
On completion: record evidence and handoff to direct successors.
Do not merge or change production without applicable authorization.
```

Because the two leaves have no prerequisites, the operator can launch
independent workers in separate conversations using these commands:

```text
AGENT-CMD SPINUP recorder-ticket-worker.pmd "issue"="101" "version"="V2"
@recorder-ticket-worker.pmd
```

```text
AGENT-CMD SPINUP recorder-ticket-worker.pmd "issue"="102" "version"="V2"
@recorder-ticket-worker.pmd
```

**Only after both leaf handoffs are independently accepted**, a third
worker may be launched for the convergence ticket:

```text
AGENT-CMD SPINUP recorder-ticket-worker.pmd "issue"="103" "version"="V2"
@recorder-ticket-worker.pmd
```

If #101 checkpoints, the next conversation does not automatically claim
it again.  The worker verifies the original session and resumes it when
authorized.  If another agent must replace that owner, the operator
explicitly requests transfer, and the worker audits the handoff first.

All three example issues and the repository name are illustrative.

## 5. Command-generation convention

When preparing a command for another ChatGPT conversation, output one
independently copyable complete SPINUP invocation for **each** worker.  The
filename in the command and final attachment line must match the authored
PMD exactly.  Put the `@filename.pmd` mention on the **last separate line**
of each command block:

```text
AGENT-CMD SPINUP example-worker.pmd "issue"="123" "version"="V2"
@example-worker.pmd
```

The person launching the worker must select the actual attachment in the
ChatGPT `@` picker if plain text does not resolve it.  Printing a command
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

## 7. Project Settings instructions (copyable block)

Copy **only** the contents of the Markdown fence below into the
relevant ChatGPT Project Settings -> Instructions field.  This is a
short routing rule, not a substitute for the full authoring standard
or the general AGENT-CMD protocol.  Keep the block distinct from
the illustrative examples above.

```markdown
## AGENT-CMD PMD authoring

RepoWorkflow is the version-controlled authority for the general
`AGENT-CMD-PROTOCOL.md` and task-specific `PMD_AUTHORING.md`.
When authoring or revising a `.pmd`, read `PMD_AUTHORING.md`
from `Ma-XX-oN/RepoWorkflow` at its applicable approved revision.
Use the general AGENT-CMD protocol for command execution.

Every `.pmd` must declare its exact filename and prompt version.
Every SPINUP must include the matching `"version"` argument.
On mismatch, STOP before any claim or mutation and report both versions.
The version identifies only the prompt revision, not worker ownership.
Existing issue claims remain valid across PMD revisions.  Resume
the verified original claim; transfer only when explicitly requested
and after the ownership handoff is verified and recorded.

For ticket workers, follow the authoring guide's repository-qualified
issue mapping, dependencies, acceptance, evidence and handoff rules.
For other worker types, do not invent ticket-specific requirements.
Keep generic protocol rules separate from task-specific PMD instructions.

When generating SPINUP commands, make each independently copyable
and put the matching `@filename.pmd` on the final line.
Repository changes do not automatically update Library/Project
attachments or already-running workers; verify the runtime copy.
```

**Do not copy the example ticket numbers or SPINUP commands** into
Project Settings; they illustrate the authoring convention only.

## 8. Review checklist

- Is the declared PMD filename correct and the literal version unambiguous?
- Does a mismatched supplied `$version` stop **before** any mutation?
- Does a new version preserve all existing ticket claims by default?
- Is scope task-specific and free of duplicated generic protocol machinery?
- Are required arguments, acceptance results and ownership boundaries clear?
- Are issue numbers repository-qualified and graph edges direct, if relevant?
- Are external/browser evidence and integration owners distinguished?
- Does each generated command end with its exact `@filename.pmd` line?
- Are repository and Library copies clearly distinguished and verified?
- Have security, merge and production approvals been preserved?
