# Source Size and Single-Read Rationale

**Status:** Authoritative explanation of the existing source-size gate. The
enforced limit remains in `tests/test_source_size.py`. For semantic-preserving
refactoring, see [DOCUMENTATION_STRUCTURE.md](DOCUMENTATION_STRUCTURE.md).

## Why the 500-line rule exists

The rule has two related purposes:

1. **Maintainability.** Encourage cohesive, focused source files and documents.
   When a file mixes responsibilities, extract a coherent module or companion
   document without weakening requirements, examples, assertions or rationale.
2. **Agent retrieval and context efficiency.** Keep each file small enough for
   an agent to read **entirely in one response** with comfortable headroom under
   tool-response/context budgets. Avoid normal workflows that require multiple
   source reads, chunk assembly or reconstruction.

The historic approximately 10,000-token figure concerned a **tool-response
budget**, not the model's entire context window. Neither a 500-line count nor
a byte count directly measures token usage. The line ceiling is a practical
structural safeguard, **not an established technical truncation threshold**.

The test rejects covered files with **500 or more lines**; the accepted
maximum is therefore **499**. The authoritative set of checked paths is
defined by the test, not by this document.

## October 13, 2026 discussion: proposed thresholds, not measurements

The discussion considered a **6,000-token warning**, **8,000-token hard
threshold**, and approximately **10,000 tokens for a relevant task working
set**. These were *proposals*, not an implemented token budget or an experimentally
proven universal connector cutoff. The current source-size gate enforces
lines, not these token thresholds. Do not claim token validation is active.

A token estimator must name its tokenizer and account for response framing;
otherwise its measurements cannot establish an exact response ceiling.
Token budgets should be calibrated by controlled measurements rather than
guessed from line counts.

## October 31, 2026: read-only GitHub connector experiment

**Repository:** `Ma-XX-oN/RepoWorkflow`

**Pinned commit:** `b7f39e33837bcbb9e22cd88bb63222d3149b416d`

**Method:** One unrestricted `fetch_file` call per file. The returned
content was compared with an independent `raw.githubusercontent.com` read,
the pinned Git tree's declared blob byte length, and its Git blob identity.
No chunking or reconstruction. UTF-8 byte counts were measured on the
returned strings. The six first-pass samples were:

| File | Authoritative UTF-8 bytes | Result |
| --- | ---: | --- |
| `tests/test_dependency_comparison.py` | 2,003 | Complete |
| `repo_workflow/repo_info_adapter.py` | 6,026 | Complete |
| `tests/test_done_planner.py` | 12,070 | Complete |
| `tests/test_hosted_version_identity.py` | 20,018 | Complete |
| `FIRST_USE_WORKFLOWS.json` | 38,246 | Complete |
| `tests/test_first_use_lanes.py` | 44,799 | Complete |

The largest three samples (20,018; 38,246; 44,799 bytes) were each
retrieved **three additional times**, with expected byte counts each time:
**15/15 single-call reads returned complete content**. The largest sample
had 1,465 nonempty-or-empty text lines (1,466 when counting the trailing
empty split element); it substantially exceeded 500 lines.

**What was verified:** Complete returned content at the GitHub connector
orchestration boundary, including independent raw-content equality and
authoritative byte count/blob identity on the initial six reads. Additional
repeat reads verified expected byte count, not a second full content comparison.

**What was NOT verified:** An exact model-visible token limit, the maximum
permitted tool-response size, or integrity of an entire oversized response
after direct rendering into model context. The orchestrator can handle a
large response while a model-visible representation has a separate limit.
No tokenizer-based token threshold was measured. These results do **not**
justify changing the 500-line cap or asserting that 8,000 tokens are safe.

## Operational rule

- Keep the existing line-count test while its structural policy remains in
  effect. Do not minify code or delete behavior, tests, or rationale to pass.
- Prefer files small enough to read **in one complete tool response**.
  Oversize or mixed-responsibility files should be split coherently.
- Pin exact source revisions. If a response is visibly incomplete, do not
  analyze or modify it as if it were complete; report an incomplete read
  and repair the retrieval strategy or source organization.
- **Do not prescribe multi-response chunk reconstruction as the default.**
  Its avoidance is one of the reasons this policy exists.
- Treat 6,000/8,000 tokens as research candidates only. Any replacement
  policy requires explicit authorization, a defined tokenizer, controlled
  model-visible retrieval measurements and regression coverage.

## Historical repository decisions

- [Issue #133](https://github.com/Ma-XX-oN/RepoWorkflow/issues/133)
  and merged [PR #134](https://github.com/Ma-XX-oN/RepoWorkflow/pull/134)
  require semantic-preserving document splits rather than content deletion.
- [Issue #338](https://github.com/Ma-XX-oN/RepoWorkflow/issues/338)
  and merged [PR #339](https://github.com/Ma-XX-oN/RepoWorkflow/pull/339)
  restored the strict below-500-lines invariant after a regression.

**Source of truth:** The enforcement code is
[`tests/test_source_size.py`](tests/test_source_size.py); this document
explains why it exists and preserves the limits of the retrieval evidence.
