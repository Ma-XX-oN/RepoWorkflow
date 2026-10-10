# Local evidence import for hosted validation (#70)

The importer reads immutable #69 observations and classifies each required
#95 atomic test unit as applicable, stale, missing or unusable. It never
changes the underlying result, candidate, fingerprint, runner or mode.

The host supplies two explicit independently verified proof sets:

1. trusted_record_ids: evidence IDs authenticated from retained durable
   audit/provenance, not merely IDs discovered on disk.
2. equivalent_candidate_shas: source candidates independently proven to
   have equivalent #68 per-unit effective inputs to the current candidate.

Same candidate and matching #68 fingerprint can be reused when provenance
is trusted. A different candidate requires an explicit membership in the
equivalence proof set and an equal expected #68 fingerprint, including
required runner capabilities. Untrusted, failed, incomplete and pending
results are unusable. A changed input or unproven candidate is stale.
Missing units remain missing. A manual/MIT requirement cannot be satisfied
by an automated result. Existing authenticated manual PASS is eligible;
no synthetic manual evidence is created.

The importer fails closed when trust/equivalence sets are absent, inputs
are invalid, or a durable stored record fails checksum/schema validation.
It does not infer authority from a provider run name or a successful command.

In the hosted pipeline the authentication and candidate-equivalence
providers must be implemented before using imported evidence to omit work.
This model is reusable by #110 and does not itself authorize skipping
tests in the live CI workflow.

Tests: tests/test_validation_import.py, issue-70-evidence-import.
