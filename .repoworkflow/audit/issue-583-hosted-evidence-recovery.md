# #583 hosted certification evidence recovery, 2026-10-14

The byte-for-byte original canonical JSONL, prior to correction, is retained
as `issue-583-original-hosted-log-20261014.jsonl` beside this document.
Its Git blob is `5d9a316b8fdb373ec310eb7e4d535697daa469e9`. Existing prior commits and run artifacts
also preserve the original evidence.

Hosted runs 38645336809 and 38646961035 executed local tests successfully
but concluded FAILURE because hosted immutable development-tag publication
failed. Their canonical records had already reported `succeeded` and reusable
before the complete hosting gate finished. That classification must not imply
hosted certification. Both records retain run ID, invocation, test/source SHA,
platform, and original observed local outcome, but are explicitly marked
INCOMPLETE, nonreusable, and lack claimed terminal development-version
ownership. Earlier verified PASS records remain byte-identical.

The first rejected run reused `.0.1` across different candidates. The second
run used `.0.2`, but the published `.0.1` ownership conflict in the historical
canonical log caused its terminal publisher to fail. No immutable tags were
deleted or retargeted. For the new candidate, the engine adapter increments
the CI iteration to `.0.3`. This is an evidence repair, NOT a claim that
those earlier hosted workflows passed. Underlying local test results are
preserved in the original log and immutable GitHub Actions artifacts.

The #572 hosted pipeline should independently address partial publication:
validating immutable terminal identity before classifying a provider result
as reusable. #583 does not modify or assume ownership of that implementation.
