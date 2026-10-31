# Software Engineering Best Practices

**Scope:** RepoWorkflow and all repositories using it, in any programming language, operating system, toolchain, or provider.

**Nature:** Human-readable best-practices guidance, not a claim of universal automated enforcement. Applies whenever relevant to the task. The original assignment, explicit acceptance criteria, ownership and approval rules remain controlling.

## 1. Investigate before changing

- State the required behavior and the observed departure from it, with exact source revision, environment and reproduction.
- Follow the evidence-driven Problem / Hypothesis / Action / Learning cycle in [BUG_INVESTIGATION.md](BUG_INVESTIGATION.md).
- Distinguish product defects from test-oracle errors, invalid fixtures, environment configuration, provider constraints and unavailable capabilities.
- Verify the actual platform or tool capability before attributing a failure to a limitation.
- Try the smallest officially supported configuration, invocation or API on the exact failing workflow before proposing architecture changes.
- Prefer repairing the root cause to hiding symptoms. Preserve invariants, existing data, ownership, permissions, recovery and compatibility contracts.

## 2. Design simple, reusable, maintainable code

- Prefer correct standard-library facilities and established platform APIs over bespoke path, encoding, process or transport heuristics.
- Keep components cohesive with clear responsibilities, contracts and interfaces. Do not copy the same workaround into multiple callers.
- Introduce one reusable interface for shared semantics; contain unavoidable platform differences inside narrowly scoped adapters.
- Do not widen a local correction into a redesign without verified necessity and authorization.
- Review interactions with downstream consumers and preserve intentional behavior, including negative paths.
- Validate untrusted inputs at system boundaries. Check internal invariants explicitly; do not silently turn violations into success.
- Apply the responsibility-based code and documentation guidance in [DOCUMENTATION_STRUCTURE.md](DOCUMENTATION_STRUCTURE.md).
- For the 500-line rule's single-read/context purpose, limitations, and measured
  connector evidence, follow [SOURCE_SIZE_RATIONALE.md](SOURCE_SIZE_RATIONALE.md).

## 3. Portable behavior first

Portable code provides the **same specified behavior** across the supported environments, rather than merely making different platform test suites green.

- List supported OS versions, architectures, runtimes, locales, shells, filesystems and Git/provider configurations relevant to the change.
- Keep logical identity separate from native path spelling, filesystem permissions, Git wire formats, text encoding and subprocess argument representation.
- Preserve exact bytes when bytes are authoritative. Decode with an explicitly correct encoding when text is authoritative; do not assume locale defaults.
- Use Git's documented filters, attributes and checkout machinery rather than guessing CRLF/LF/raw byte candidates.
- Never normalize away distinctions with unconditional separator replacement, guessed aliases or arbitrary character substitution.
- Do not presume POSIX signals, executable mode, junctions, symlinks, Bash, Unicode console behavior or filesystem byte-name support are universal.
- Where an OS truly lacks a capability, keep the core semantic test portable and separately test the native capability on supporting platforms. Label genuine nonapplicability accurately.
- Platform-specific code must have an identified capability reason, a narrow boundary and tests of its observable contract.
- Avoid global test monkeypatches that obscure the real invocation boundary, hidden interpreter overrides and fake-service substitution when genuine provider acceptance is required.

## 4. Test behavior, not implementation convenience

- Derive expected outcomes independently from requirements and contracts, never simply from current code.
- Reproduce a regression RED before fixing it; prove the same requirement GREEN afterward, including relevant negative paths.
- Preserve prior assertions and all applicable acceptance requirements. Do not weaken a test or reinterpret a failure just to obtain GREEN.
- Test the exact final revision on each required native platform. A fixture, one OS, a historical revision, a partial test suite, or an emulator cannot stand in for that evidence.
- Exercise adversarial boundaries that matter: Unicode and encodings, line endings, path identity, links and reparse points, process invocation, permissions, filesystem capabilities, stale provider state and recovery.
- Report PASS, FAIL, SKIP, INCOMPLETE and N/A separately. Every skip needs its reason, applicability decision and alternate coverage when semantics remain required.
- Provider mocks verify isolated logic; they do not certify live authority, provider writes or durable independent readback.
- Follow the authoritative adequacy and evidence requirements in [TEST_ADEQUACY.md](TEST_ADEQUACY.md).

## 5. Coordinate integration without causing regressions

- Establish one owner for each modified shared file or interface; check active claims before writing.
- Incorporate verified changes without overwriting other accepted work. Reconcile overlapping behavior semantically, not by indiscriminate copy or mechanical substitution.
- Reverify the assembled exact revision after integration. Earlier child-branch results remain historical evidence, not assembly certification.
- Preserve genuine failure, timeout, incomplete, unknown and rollback distinctions, including provenance and readback.
- Respect protected branches, provider authority, approval gates and explicit release boundaries.

- A downstream ticket executing speculatively owns integration of the
  upstream accepted result into its own work, exact-revision retesting, and
  the evidence-based DONE handoff. Its dependants are not unblocked by
  preparatory progress or upstream DONE alone. Follow the authoritative
  [work scheduling contract](WORK_GRAPH_SCHEDULING.md).

## 6. Evidence-based review and completion

Before declaring work complete, answer:

1. What authoritative requirement was satisfied, and what revision/configuration was reviewed?
2. What root cause and supported remedy were verified?
3. Which supported platforms and meaningful failure paths were actually exercised?
4. What was skipped, deferred or not applicable, and why?
5. Did code review find new heuristics, hardcoded platform assumptions, weakened tests or ownership collisions?
6. Was the final integrated revision verified, or only an earlier candidate?
7. Are any requirements unverified, blocked or owned by another worker?

State **I don't know** when evidence is absent. Do not call a documented recommendation an automatically enforced rule, or a green test proof of defect-free code. Record unresolved requirements and the next authorized owner rather than inventing completion.

## 7. Applicability and discoverability

This is the general engineering entry point for AI coding agents and humans examining RWF. Read it at task intake, then follow the linked authoritative specialist documents. Consumer projects should link to this document at their pinned RWF revision when applying its guidance; they retain their own more specific requirements. New guidance belongs here only if it is broadly applicable, while domain-specific contracts retain one authoritative home.

## 8. Durable issue checkpoints and context recovery

GitHub issues are the durable record for ongoing engineering work, not merely
messages to other agents. Maintain each active issue so that a new engineer or
AI agent with **zero prior conversation context** can resume accurately.

- Record the original objective and every remaining acceptance criterion, not
  just the most recent subtask or latest test result.
- Identify repository, branch, PR, exact source/target SHAs, configuration,
  assigned ownership, approvals and prohibited actions.
- Distinguish completed changes and their exact evidence from partial tests,
  historical runs, fixture evidence, skipped checks, failures and unknowns.
- Record root-cause findings, decisions, rejected approaches, integration
  conflicts, unresolved dependencies and responsible owners.
- Maintain a clear PASS / FAIL / INCOMPLETE / DEFERRED ledger and the **next
  executable authorized action**. State any genuine blocker precisely.
- Update the issue after material source changes, tests, defects, decisions,
  ownership or integration transitions, and **before ending an execution
  window**. A chat status message or a commit alone is not a checkpoint.
- Read and reconcile the issue's latest authoritative checkpoint before work
  resumes; never assume stale notes or a different agent's result proves
  current acceptance. Avoid duplicate reports and do not alter ownership merely
  because another agent supplied a checkpoint.

This policy applies even when the **same agent** continues the work. A
checkpoint is successful only when a context-free reader can distinguish the
original mission, verified progress, unfinished work and immediate next step.
Keep tickets current without creating new automation gates or claiming that
written documentation alone guarantees compliance.

**Core principle:** Verify first. Prefer the simplest supported, portable, contract-preserving fix. Prove behavior on the actual target platforms and exact revision. Never mask missing evidence as success.
