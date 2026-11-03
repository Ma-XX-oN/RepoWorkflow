# Dependency Pause and Fix Propagation Gate

Status: proposed repository-wide coordination procedure. The current #660 / #109 pause is an explicit operator
instruction, recorded on affected GitHub issues. This document does not itself alter formal lifecycle state,
grant file ownership, or authorize merges.

## Mandatory scheduling check

Before generating an AGENT-CMD prompt, starting or resuming a worker, or declaring a ticket READY or DONE:

1.  Read the current documentation index, execution standard, relevant issue, accepted source SHA, and
   canonical relationship graph. Include descendant/transitive closure, not just the current umbrella's
   immediate leaves.
2.  Reconcile canonical graph against current issue-owned dependency statements; report divergences, missing
   edges and affected scope. Do not invent an edge merely because another owner controls a file.
3.  Check **explicit operator pause gates** on the ticket and every relevant ancestor. An explicit pause
   overrides ordinary READY and independent leaf completion for scheduling. Mark the ticket PAUSED in status
   prose; the five PG glyphs do not create a new formal lifecycle state. Do not issue a launch prompt that
   would execute a paused ticket.
4.  For cross-ticket failures, classify product defect, test oracle, workbench/provider gate, or
   source-integration conflict. Only a verified required deliverable establishes a new execution dependency.
   File ownership and communication are not themselves dependency edges.
5.  Do not confuse a previously accepted leaf with the exact integrated candidate; preserve accepted SHA,
   changed file/blob hashes, run IDs, platform counts, skips and failing or unverified criteria.

## Fix once, propagate to every affected consumer

Maintain a durable **propagation ledger** at the owning issue and at every paused/downstream consumer:

| Field | Required evidence |
| --- | --- |
| Origin | owner issue, PR, accepted source SHA, exact changed blob(s) |
| Contract and test | reproduced RED, accepted behavior, official/native/provider GREEN or explicit incompletes |
| Affected consumers | direct and transitive graph consumers, paused branches, cross-workstream interface consumers |
| Per-consumer state | NOT REQUIRED / PENDING / IMPORTED / VERIFIED, target SHA and owner |
| Revalidation | invalidated acceptance, prescribed test, native/provider results, exact SHA |
| Resume | operator pause lifted, #660 gate verified DONE, required imported fixes VERIFIED, acceptance re-read |

Source-owner DONE is not propagation DONE. A downstream owner imports accepted source only within authorized
integration scope and verifies the new exact assembled revision. Preserve unmerged evidence and known failure
histories. Do not automatically resume merely because an upstream issue closes or a test succeeds.

## Explicit #660 gate on #109 and descendants

Operator direction, 2026-11-03: **PAUSE #109 and all its descendants until #660 is independently verified DONE.**

Current issue evidence identifies #109 -> #583 -> #677 as a downstream certification chain. The currently
committed `.repoworkflow/tickets.csv` instead shows #109 -> #56 -> #51 and does **not** encode the #583/#677
chain. Both observed sets have been marked with explicit pause notices; this mismatch must be reconciled
against the authoritative current relationship store before asserting a complete descendant set. No other #109
prerequisite or unrelated sibling is suspended by inference.

During the pause: preserve existing ownership/branches, historical tests and provider artifacts; record
verified fixes from #660 and their required consumers. Do not perform implementation, certification,
integration, successor dispatch, merges or production activation for the paused tickets. Do not mark formal
lifecycle DONE/aborted on account of the scheduling pause.

Resume requires **all**:
1.  #660's original umbrella acceptance ledger is fully VERIFIED DONE, not merely leaf handoff, issue comment
   or successful focused test.
2.  The explicit operator pause is lifted or its stated '#660 DONE' condition has been verified from current
   authority.
3.  Required corrected blobs are imported into each affected consumer by its authorized owner/integrator and
   tested against its exact target SHA.
4.  The descendant set, conflicting graph records, remaining acceptance and ownership are checked again; issue
   pause notices and propagation ledgers are updated.

If any check fails, remain PAUSED, report the exact unmet condition, and do not generate an execution prompt
for that ticket.

## Human-facing PG and handoff

Show all known blocking work and external cross-ticket compatibility conflicts needed to understand
completion. Use one node per actual ticket; never duplicate nodes for 'original' and 'corrective' stages.
Preserve direct dependency edges; show non-edge coordination distinctly in prose, rather than inventing graph
relationships. A pause is an explicit annotation, not a sixth PG glyph.

At each checkpoint report: PAUSED ticket IDs, source of descendant derivation, conflicting graph evidence, fix
propagation state, remaining original acceptance, and the one condition that permits resumption. Record this
in GitHub issues so blank agents do not depend on chat memory.

Related authority: [WORK_GRAPH_METHODOLOGY.md](WORK_GRAPH_METHODOLOGY.md),
[WORK_GRAPH_SCHEDULING.md](WORK_GRAPH_SCHEDULING.md),
[AGENT_EXECUTION_STANDARD.md](AGENT_EXECUTION_STANDARD.md), and [BEST_PRACTICES.md](BEST_PRACTICES.md).
