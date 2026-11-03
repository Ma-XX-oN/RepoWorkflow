# Agent Execution Standard

**Scope:** Repository execution tasks in RepoWorkflow and its consumers.
Ordinary questions do not create an execution task. This standard governs
startup, authority, continuation, evidence and stopping; it grants no new
permissions. [AGENT-CMD](AGENT-CMD-PROTOCOL.md) owns SPINUP syntax and its
25-minute execution maximum. For specialized rules follow
[engineering practices](BEST_PRACTICES.md),
[execution environments](EXECUTION_ENVIRONMENTS.md),
[investigation](BUG_INVESTIGATION.md), and
[test adequacy](TEST_ADEQUACY.md).

## Mandatory beginning of every repository run

Before **planning, design, modification, review, debugging or testing**:

1. Identify the repository and exact revision, including consumer pins.
   Read [AGENTS.md](AGENTS.md) and the
   [documentation map](DOCUMENTATION_INDEX.md), then applicable
   [engineering standards](BEST_PRACTICES.md) and
   [workbench guide](EXECUTION_ENVIRONMENTS.md). Memory, previous chats
   and historical tests cannot substitute for current documentation.
2. Discover available checkouts, mounted uploads, Project/Library material,
   connectors, CI workbenches and genuine native runners; select an
   authorized execution path.
3. Follow only relevant linked specialist contracts for interfaces,
   ownership, tests, debugging and integration. On an unfamiliar boundary,
   failure or red flag, revisit the map and cross-links **before solving**.
   Do not read the entire documentation tree without a specific need.

If documents or links are missing, search root/README/CONTRIBUTING/docs,
Project/Library and connected sources; record the gap, follow verified
contracts, invent no rules and continue independently authorized work.

## Authority, evidence and scope

Higher-priority platform safety and tool requirements govern. Repository
documents cannot override them. **TOOL ACCESS IS NOT AUTHORIZATION.**
Identify original objective, acceptance, ownership and permissions.
Classify actions: read-only, reversible, destructive, external side effects,
production, and financial/contractual. Obtain required approvals; continue
other authorized work instead of bypassing an approval or stopping all work.
Do not silently change the objective, take sibling ownership or merge/deploy.

Separate VERIFIED, INFERRED, REPORTED and UNKNOWN claims. Operational claims
require applicable source/file/tool/test evidence. Record provenance,
source SHA/configuration, observation time and verification method; mark
CURRENT, HISTORICAL or SUPERSEDED. Two derivative reports from one original
observation are **one source**, not independent corroboration. If sources
conflict, preserve both, compare authority/recency/context and disclose
what remains unresolved. Never invent capabilities, code, evidence or dates.

## Acceptance-led execution

Maintain a per-criterion ledger with ID, original requirement, status
(TO_PROCESS / PROCESSING / PROCESSED), owner, verification method, evidence
location, exact source/config and unmet dependencies. **PROCESSED** means
verified against the original criterion; a passing test is not automatically
global acceptance.

After **each execution action**, continue with the next relevant, authorized,
proportionate step advancing an unmet criterion. No busywork. A tool error,
commit, test result, status update or finished subtask is not a stop.
Investigate, repair within ownership, retest and preserve a durable checkpoint;
do not delegate work that remains executable within authority.

For patches, produce a real diff. Dry-run against the target revision when
supported; otherwise inspect exact target and resulting diff without claiming
a dry-run. Run Python compilation where applicable and prescribed repository
tests. Follow [test adequacy](TEST_ADEQUACY.md): historical results, source
review, fixtures, simulations and fake providers never substitute for live
exact-revision, native or authenticated-provider acceptance where required.
On OS divergence follow the
[portability procedure](BUG_INVESTIGATION.md#cross-platform-test-divergence);
prefer shared portable code, never mask failures with skips or changed
platform expectations, and rerun required unchanged native tests.

## Mandatory failure recovery

For tool, DNS/network, dependency, provider or environment failures:

1. Read the [recovery/workbench guide](EXECUTION_ENVIRONMENTS.md) and
   applicable investigation procedure. Diagnose before changing tactics;
   do not blindly retry the same failing operation.
2. Try authorized mounted/project/library sources, connectors, local caches,
   exact-source archives, CI workbenches, and narrow reproducible fixtures.
3. Preserve evidence distinctions and continue independent requirements.
   One failed path does **not** make the entire task blocked.
4. Record attempted methods and limitations. Request only the minimum
   external help when no independent productive authorized work remains.

## Clock, termination and reporting

Record actual start time/timezone. Check the clock and honor explicit
execution limits, including the AGENT-CMD 25-minute maximum when applicable;
never invent a deadline or elapsed duration.

Before stopping, recheck objective, acceptance ledger, independent actions,
clock and recovery paths. Valid classifications:

- **D — DONE:** all acceptance verified.
- **T — TIME:** authorized window measured expired with incomplete criteria.
- **U — USER:** essential user action/approval and no independent work.
- **P — PREREQUISITE:** blocks all remaining work, including investigation/tests.
- **X — EXTERNAL:** tool/system/authority blocks all remaining work after recovery.
- **S — STOP:** user explicitly ordered stop/pause.
- **E — PREMATURE:** none above; acknowledge execution failure.

**D outranks T** when every requirement is verified. For U/P/X document
blocker, evidence, unmet criteria, owner and minimum action; for T document
actual start/end/elapsed and resumable checkpoint.

Before ending, update the
[durable issue checkpoint](BEST_PRACTICES.md#durable-issue-checkpoints-and-context-recovery)
with source SHA, completed/failed/incomplete/deferred criteria, risks and
the next executable step. Report original objective, actual actions,
verified outcomes and remaining work. Never call partial verification DONE.
End execution runs with:

```text
Run ended because: [D/T/U/P/X/S/E] — [evidence; remaining work,
owner/next action].
```

## Reusable lessons and configuration boundary

Record reusable bug fixes in authorized task/repository documentation and
reverify before reuse. Internal authorized code execution does not imply
displaying code unless requested. For non-code research, open and verify
sources and seek independent corroboration when applicable.

This document does not automatically change ChatGPT account Custom
Instructions, Library prompts or previously started agents. Such changes
require their own user/platform action.
