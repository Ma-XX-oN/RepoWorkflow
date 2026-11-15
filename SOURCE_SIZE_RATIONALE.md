# Source Size and Single-Read Rationale

**Status:** Authoritative explanation of the existing source-size gate. The
enforced limit remains in `tests/test_source_size.py`. For semantic-preserving
refactoring, see [DOCUMENTATION_STRUCTURE.md](DOCUMENTATION_STRUCTURE.md).

## Why the 500-soft / 800-hard rule exists

The rule has two related purposes:

1. **Maintainability.** Encourage cohesive, focused source files and documents.
   When a file mixes responsibilities, extract a coherent module or companion
   document without weakening requirements, examples, assertions or rationale.
2. **Agent retrieval and context efficiency.** Keep each file small enough for
   an agent to read **entirely in one response** with comfortable headroom under
   tool-response/context budgets. Avoid normal workflows that require multiple
   source reads, chunk assembly or reconstruction.

### Original technical source of the 10,000-token limit

The figure comes from the **`functions.exec` code-execution tool's output
contract**, which states: "Total output is capped at 10,000 tokens; longer
output is truncated." It is a limit on the tool's **model-visible returned
output**, not on the model's entire context window and not a documented
universal limit for every GitHub connector operation.

In the October 13, 2026 experiments, two independently observed
truncations reported:

| Original output tokens | Omitted tokens | Retained tokens |
| ---: | ---: | ---: |
| 28,887 | 18,887 | 10,000 |
| 14,869 | 4,869 | 10,000 |

The displayed truncation notice reported the original token count. The
exactly 10,000 retained tokens in both cases corroborated the execution
tool's documented cap. The reported truncation could remove content from
the **middle** while preserving beginning and ending material. This is why
seeing the last line alone is not a proof of complete source retrieval.

**Reference:** `functions.exec` tool description supplied by the ChatGPT
execution environment (operational tool contract; no stable public URL).
Recheck that contract if the tool implementation or environment changes.
This record preserves the observed numbers and their provenance without
claiming that the limit applies to unrelated tools.

Neither a 500-line count nor a byte count directly measures token usage.
The line ceiling is a practical structural safeguard, **not an established
technical truncation threshold**.

The current policy has a **500-line soft review threshold** and an
**800-line hard ceiling**. At 500–799 lines, review cohesion and readability,
but do not split a focused file solely because it exceeds 499 lines. At
800 lines or more, the authoritative size test fails; refactor by genuine
responsibility boundaries without losing requirements, semantics or tests.
The authoritative set of checked paths is defined by the test.

## October 13, 2026 discussion: proposed thresholds, not measurements

The discussion considered a **6,000-token warning**, **8,000-token hard
threshold**, and approximately **10,000 tokens for a relevant task working
set**. These were *proposals*, not an implemented token budget or an experimentally
proven universal connector cutoff. The current source-size gate enforces the 800-line hard ceiling,
not the proposed token thresholds. Do not claim token validation is active.

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
No tokenizer-based token threshold was measured. These results did not, by themselves, establish a universal safe line or
token ceiling. The later hosted tokenizer experiment below adds one measured
800-line sample; neither experiment proves every 800-line file fits.

## October 31, 2026: hosted 800-line tokenizer verification

**Independent execution:** [GitHub Actions run 41210454306](https://github.com/Ma-XX-oN/RepoWorkflow/actions/runs/41210454306);
job `124564151325` completed with **SUCCESS**.

A dedicated, temporary workflow installed `tiktoken==0.12.0` on a hosted
Ubuntu runner and checked out pinned RepoWorkflow commit
`b7f39e33837bcbb9e22cd88bb63222d3149b416d`.
It measured the first 800 lines of `tests/test_first_use_lanes.py`,
joining the original lines and removing the final newline from the sample.

| Property | Verified result |
| --- | --- |
| Sample | First 800 Python source lines |
| UTF-8 bytes | 24,837 |
| Tokenizer | `tiktoken` 0.12.0 |
| Encoding | `o200k_base` |
| Encoded tokens | **6,456** |
| Proposed 8,000-token ceiling | **PASS** (1,544-token headroom) |
| Sample SHA-256 | `506eb1c73567a426d26452b2d85c04f39cc1ed467f5ae74d7d07951b2d30cff0` |

**Reproducibility:** The temporary workflow is at commit
`0a2c42a6817d89707f7fe8f51d8058e8eb1eea7e` on branch
`experiment-800-line-tiktoken-20261031`. The Actions log includes the
`RWF_TOKEN_RESULT` record with the encoding, version, bytes, token
count, threshold comparison, and sample digest.

**Scope of proof:** This one representative 800-line Python sample is
below 8,000 tokens using the named tokenizer, and the hosted workflow
finished successfully. It does **not** guarantee that every 800-line file
fits, prove a general model-visible token cutoff, or authorize changing
the repository source-size test. The earlier single-response retrieval
experiment and this tokenizer measurement are distinct checks.

**Adopted policy:** A 500-line soft review threshold and an 800-line
hard ceiling, complemented by the existing 80-character soft and
120-character strong line-width guidance. The source-size test enforces
the 800-line ceiling; 500 lines prompts review, not test failure.

## Operational rule

- Apply 500 lines as a soft cohesion review trigger and 800 lines as the
  hard gate. Do not minify code or delete behavior, tests, or rationale to pass.
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
