# Inline executable-test policy

Ticket executable-test sections are for small preliminary contract checks, not general source-code storage.

Version 1 limits are:

- at most 8 inline tests per issue;
- at most 4096 UTF-8 bytes in one test body;
- at most 16384 UTF-8 bytes in the complete structured test section.

RWF validates limits on import and export. Oversized content fails and is never truncated, compressed, or silently rewritten.

When ticket tests differ from trusted repository tests, RWF presents a unified diff and warns that acceptance permits the proposed code to execute through its declared evaluator. The warning ends with the explicit `rwf tests accept` command. Generating the review never executes code or grants trust.

If practical use requires larger tests, keep them in repository-owned files. A reference mechanism should be designed only when an observed use case requires it.
