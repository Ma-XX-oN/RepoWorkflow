# Documentation Map

Start here when investigating, implementing, testing or operating RepoWorkflow.
Read the **shortest relevant path**; follow a specialist link only when the
task requires its contract. Documents linked below retain their own authority.
This map does not replace task acceptance, ticket ownership or approval gates.

## Solve a problem

1. [Engineering overview](BEST_PRACTICES.md): investigate, design and verify.
2. [Investigation procedure](BUG_INVESTIGATION.md): repeatable evidence cycle.
3. [Execution environments](EXECUTION_ENVIRONMENTS.md): choose a runner or
   workbench on any authorised CI provider when local tools lack dependencies.
4. [Testing and proof](TEST_ADEQUACY.md): distinguish fixtures, native runs,
   hosted evidence and provider certification.
5. [Current work](CURRENT_WORK_STATE.md): check active coordination context;
   confirm freshness against the actual issues and source revisions.

## Understand the product

- [Architecture](DESIGN.md) -> [public interface](PUBLIC_WORKFLOW.md)
  -> [command grammar](COMMAND_GRAMMAR.md)
  -> [grammar tests](COMMAND_GRAMMAR_TESTS.md).
- [Lifecycle](WORKFLOW_LIFECYCLE.md) ->
  [six-state lifecycle](SIX_STATE_LIFECYCLE.md) ->
  [state layout](STATE_LAYOUT.md) ->
  [recovery](STATE_RECOVERY.md).
- [Work graph](WORK_GRAPH_METHODOLOGY.md) ->
  [scheduling](WORK_GRAPH_SCHEDULING.md) ->
  [testing](WORK_GRAPH_TESTING.md) ->
  [visual conventions](WORK_GRAPH_VISUAL_CONVENTIONS.md).
- [Integration](WORKFLOW_INTEGRATION.md) ->
  [done planner](DONE_PLANNER_CONTRACT.md) ->
  [release](STABLE_RELEASE.md).

## Perform a focused task

- **CI and test execution:**
  [Execution environments](EXECUTION_ENVIRONMENTS.md) ->
  [test strategy](TEST_STRATEGY.md) ->
  [on-demand CI contract](CI_INVOCATION_CONTRACT.md) ->
  [risk-scoped certification](RISK_SCOPED_CI_CERTIFICATION.md).
- **Documentation and code size:**
  [Structure policy](DOCUMENTATION_STRUCTURE.md) ->
  [source-size rationale and measurements](SOURCE_SIZE_RATIONALE.md).
- **Agent scheduling:**
  [AGENT-CMD protocol](AGENT-CMD-PROTOCOL.md) ->
  [PMD authoring](PMD_AUTHORING.md) ->
  [prompt packaging](AGENT_PROMPT_PACKAGING.md).
- **First use and adoption:**
  [Adoption](ADOPTION.md) ->
  [first-use test strategy](FIRST_USE_TEST_STRATEGY.md) ->
  [first-use audit](FIRST_USE_WORKFLOW_AUDIT.md).
- **Host and metadata:** [repository info](REPO_INFO_CONTRACT.md) ->
  [issue metadata](ISSUE_METADATA.md) ->
  [ticket dependency adapter](TICKET_DEPENDENCY_ADAPTER.md).
- **Operational diagnostics:** [lane diagnostics](LANE_DIAGNOSTICS.md) ->
  [lane cache refresh](LANE_CACHE_REFRESH.md) ->
  [graph display](LANE_GRAPH_DISPLAY.md).

## How this documentation system is maintained

The recursive hierarchy, authoritative ownership, placement rules,
link validation and cross-cutting navigation policy are defined in
[DOCUMENTATION_STRUCTURE.md](DOCUMENTATION_STRUCTURE.md), under
**Documentation architecture**. Read it before adding or moving docs.

## Navigation rules

- Each topic starts with a compact overview and links to focused procedures.
- Follow deeper links only to resolve the current question; use cross-topic
  links where a boundary crosses source, CI, lifecycle or provider evidence.
- Do not copy authoritative specifications into this index. Keep one owner
  per contract and link to it.
- A failed local installation is **not** proof that hosted runners cannot
  install the dependency. Consult [execution environments](EXECUTION_ENVIRONMENTS.md)
  before declaring an external-tools blocker.
