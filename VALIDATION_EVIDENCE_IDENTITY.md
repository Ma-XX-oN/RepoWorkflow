# Validation evidence identity contract (#68)

Status: frozen v1 interface for successor #95.

## Semantic identity versus provenance

The reusable evidence identity is a deterministic fingerprint for one test
unit and its **effective correctness-relevant inputs**. It is not a branch
name, Git commit SHA, provider job ID, run timestamp, or command invocation.
Changes to unrelated source do not invalidate a unit when a verified
dependency closure proves those inputs are irrelevant.

Candidate SHA, base, branch, version, executed runner/platform, result,
provider run identity and immutable audit metadata remain separate evidence
provenance. #95 and #69 must validate applicability and provenance in addition
to comparing fingerprints. Matching hashes alone do not establish PASS.

## Canonical manifest (schema rwf-validation-input-v1)

The identity object contains exactly:

* schema: literal rwf-validation-input-v1.
* unit: stable semantic test-unit identifier.
* source: relevant effective source path to SHA-256 byte digest.
* catalogue: effective test definition/selection path to byte digest.
* configuration: relevant test/build/configuration path to byte digest.
* workflow: applicable workflow/adapter semantics path to byte digest.
* capabilities: required semantic runner/runtime feature key to versioned value.

All five sections are explicitly supplied, nonempty and maps of string keys to
string values. File sections use lowercase 64-digit SHA-256 content digests.
The caller must enumerate the **complete per-unit dependency closure**.
When completeness is unknown, reusable evidence MUST NOT be accepted.
Conservative extra inputs are allowed; omitted relevant inputs are not.

File keys denote stable repository-relative paths or explicitly named virtual
inputs, with digest values representing *effective* bytes after any
deterministic expansion. Capabilities must include every requirement that
changes test behaviour (e.g. OS, architecture, interpreter/toolchain version,
declared feature availability). Provider names and ephemeral runner properties
are not semantic inputs unless they affect correctness, in which case
capture them as declared capabilities/workflow semantic bytes.

Inputs use NFC Unicode, no leading/trailing whitespace and no control
characters in names/values. Missing, empty, invalid, or unknown fields fail
closed. Map ordering is irrelevant. Canonical encoding is ASCII-escaped JSON
with sorted keys, compact separators, no NaN, and SHA-256 over encoded bytes.

A changed relevant unit, file digest, workflow/configuration digest or
capability produces different canonical bytes and a different
collision-resistant fingerprint. Local and hosted executions MUST use the same
function and input schema. No local/hosted location flag is part of the hash.

## Downstream contract

#95 defines required-unit applicability, coverage aggregation, stale/missing
states and conservative invalidation; fingerprint equality alone never grants
coverage. #69 handles durable, append-only records/provenance and coordinates
with #57. #70 verifies imported local evidence against hosted requirements.
#110 only schedules missing automated work; automated MIT evidence is forbidden.

Validation: unit acceptance tests in tests/test_evidence_identity.py.
Provider-backed CI and exact head checks must be verified before DONE.
