# Portable Ticket Write Contract

Status: provider-neutral write companion to the read-only `repo-info` contract.

Core RWF invokes the configured `ticketCommand` as:

```text
ticket-write issue body replace ISSUE EXPECTED_BODY_SHA256 BODY_FILE
```

The adapter must compare the current provider body with the expected digest before replacement and confirm the resulting provider body afterward. A stale precondition, provider failure, malformed response, or unknown/partial outcome is failure, never success.

Successful output is exactly:

```json
{"schema_version":1,"number":123,"body_digest":"<sha256-of-new-body>"}
```

Core validates issue identity and the digest of the requested replacement. The body is supplied by file rather than command-line text to avoid argument-length and quoting hazards.

`repo-info` remains read-only. Provider-specific code, including the supplied GitHub adapter, remains outside core workflow semantics.
