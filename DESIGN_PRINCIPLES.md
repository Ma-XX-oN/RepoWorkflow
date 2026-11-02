# Engineering Design Principles

**Scope:** Reusable engineering guidance for RepoWorkflow and consumer
repositories. RepoWorkflow's primary job is mechanical, evidence-backed state
transitions; it also promotes maintainable code through the design choices
used to implement those transitions.

These are review principles, not claims of automated enforcement. Task
contracts, acceptance criteria, permissions, and ownership remain controlling.
Start with [best practices](BEST_PRACTICES.md) for the general workflow, and
[architecture](DESIGN.md) for RWF-specific component responsibilities.

## 1. Keep one authoritative implementation

- Implement a behavior once. Reuse the same parser, dispatcher, command handler,
  state transition, and result semantics from every supported entry point.
- Prefer composing existing operations to copying their logic into another
  provider, platform, command, or workflow.
- When a feature changes *how* an operation is invoked, observed, or transported,
  wrap the existing operation rather than modifying every implementation.
- Keep cross-cutting assertions, diagnostics, auditing, and capture at one
  coherent boundary. Do not scatter the same condition through many handlers.
- Avoid a new abstraction if an existing interface already expresses the
  required behavior. Extend the smallest suitable boundary.

## 2. Separate mechanisms from policy and transport

- Keep mechanical state-transition rules, guards, and evidence authoritative
  in the RWF engine. Do not reimplement them in CI workflow files or adapters.
- Keep GitHub and other provider details behind portable adapter contracts.
  Platform-specific behavior belongs behind one narrow capability boundary.
- Separate an operation from its transport: local and hosted execution should
  invoke the same operation; hosted transport adds only request delivery,
  execution-context setup, result capture, and publication.
- A command wrapper should preserve the original command's arguments,
  meaningful output, exit status, and observable state-transition behavior.

## 3. Optimize for minimal change and minimal duplication

- Start by identifying existing functionality that already meets part of the
  requirement, then add only the missing capability.
- Prefer the smallest supported change that satisfies the full contract and
  its negative paths; do not redesign neighboring components speculatively.
- A useful abstraction removes repeated responsibilities or centralizes an
  invariant. An abstraction that merely relabels one call adds overhead.
- Avoid redundant Git subprocesses, provider requests, reparsing, discovery,
  and repeated validation of facts that have not changed. Preserve correctness
  and concurrency guarantees while reducing work.
- Optimize for long-term readability and maintenance as well as line count.
  Fewer lines are beneficial only when behavior and invariants stay explicit.

## 4. Make boundaries verifiable

- State preconditions, postconditions, identity, ownership, and failure behavior
  at the interface responsible for enforcing them.
- Test one implementation of the business operation and separately test the
  wrapper/adapter contract. Where behavior should be equivalent, compare the
  same operation through both invocation routes.
- Verify invalid context is rejected *before* a protected transition occurs.
  Preserve the distinction between failure, pending, incomplete, and success.
- Treat local fixture tests, genuine hosted execution, and exact-revision native
  acceptance as different evidence. Do not claim a wrapper's tests prove every
  command's behavior or that historical evidence certifies a changed revision.

## 5. Example: remote invocation without a second command engine

The planned `.ci/rwf` forwarding feature (issue #660) illustrates the design,
but is **not** documented here as already implemented:

1. The hosted entry point passes the request arguments to the existing RWF CLI.
2. One centralized invocation wrapper asserts the required command-branch
   context and establishes the original execution context.
3. The wrapper calls the **same command implementation** as a local invocation.
4. The wrapper captures and publishes its return result. Individual commands
   do not gain remote-specific branches.

The reusable rule is: **change the environment around an existing operation,
not the operation itself.** This resembles a decorator around command dispatch
and an adapter at the provider boundary; the principle matters more than the
design-pattern name.

## 6. Portable semantics behind narrow capability boundaries

OS-agnostic code must preserve the **same specified behavior** across native
Windows, Linux, and macOS, rather than accumulating OS-name checks to make
each platform's tests pass.

- **Ports and Adapters (hexagonal architecture):** Keep mechanical workflow
  transitions independent of the OS, shell, filesystem, subprocess runtime,
  and CI provider. Put necessary native mechanics behind a narrow port.
- **Adapter and Facade:** Present one cohesive Git/process/path interface
  to callers. Prefer an existing portable standard-library or Git API over
  inventing a new adapter or facade.
- **Dependency Inversion:** High-level workflow rules depend on the contract
  of a capability, not on a particular operating system's implementation.
- **Strategy, only when justified:** If supported environments genuinely
  require different mechanisms, select implementations in one place behind
  the same observable contract. Avoid per-call platform branching and
  unnecessary class hierarchies.
- **Canonical identity versus representation:** Preserve repository and path
  identity independently from native separators, Git wire formats, checkout
  transformations, line endings, filename bytes, and shell spelling.
- **Capability-based decisions:** Check the required capability or use an API
  that provides it portably; do not treat OS names as proxies for capability.
- **End-to-end semantic parity:** Test exact intended behavior and negative
  paths on genuine native platforms. A platform skip is not a behavioral PASS.
  Do not weaken assertions or silently normalize meaningful differences.

**Example:** A path identity rule should rely on Git-authoritative identity
and checkout semantics where Git owns the data. The workflow transition
calls one reusable path/Git abstraction, not a succession of Windows/Linux
separator, case, encoding, and line-ending heuristics.

The central rule is **one semantic contract, narrow platform mechanics**.
Together with the remote invocation wrapper, this means cross-cutting
variation belongs at the boundary where it originates, never scattered
through the workflow state machine or individual command handlers.

For concrete portability requirements, continue with
[best practices — portable behavior](BEST_PRACTICES.md).

## Review prompts

Before accepting a design, ask: Does it duplicate an existing state transition?
Can one wrapper or adapter own the new responsibility? Does it spread conditionals
through unrelated handlers? Can local and remote behavior be compared directly?
Does it add unnecessary processes or queries? Are the negative paths preserved?

For evidence-driven changes, continue with
[bug investigation](BUG_INVESTIGATION.md),
[test adequacy](TEST_ADEQUACY.md), and
[documentation structure](DOCUMENTATION_STRUCTURE.md).
