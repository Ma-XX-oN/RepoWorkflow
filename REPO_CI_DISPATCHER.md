# Repo-CI Dispatcher

Status: implementation of the provider-neutral forwarding boundary in #91.
The semantic request and result contract is REPO_CI_CONTRACT.md (#65).

## Invocation

From a RepoWorkflow checkout on Unix or Git Bash:

```sh
repo-ci execute < request.json
```

The executable `repo-ci` must be on PATH or invoked as `./repo-ci`.
The existing executable `rwf` exposes the equivalent routed invocation:

```sh
./rwf repo-ci execute < request.json
```

An invocation accepts exactly one operation token and one JSON request on
stdin, forwards the original input bytes, and emits one JSON result on
stdout.  A rejected invocation returns nonzero with a structured JSON
error containing the semantic `code` and a non-secret `message` on stderr.
No successful evidence is returned after an adapter or transport failure.

Seven operations are accepted: `inspect-context`, `resolve-capabilities`,
`prepare`, `execute`, `publish`, `fetch`, and `check-policy`.

## Adapter selection

The consumer repository must explicitly declare `.ci/repo-ci.json`:

```json
{
  "schema": 1,
  "command": ["python", "/absolute/path/to/provider-adapter.py"]
}
```

The array is an executable and its fixed arguments.  Its exact contents
come from repository-controlled configuration, never from an issue,
branch, candidate, environment hint, or request payload.  The dispatcher
appends the operation token to this fixed command and sends the complete
original JSON request to adapter stdin.

No provider is auto-discovered.  Missing, malformed, unknown-version or
unresolvable configuration fails closed.  The dispatcher never invokes
a shell with request content.  The configured command must be installed
and accessible in the consumer's execution environment.

The provider adapter owns stage-specific execution, API calls, credential
handling, artifact transport and mapping of provider outputs.  The
dispatcher owns only v1 request/response envelopes, deterministic
selection, byte-preserving forwarding and normalized errors.  Core RWF
retains PASS/FAIL/INCOMPLETE and lifecycle decisions.

## Verification

Issue-scoped regression tests are registered under the
`issue-91-repo-ci-forwarder` group in `.ci/tests.json`.

Run the selected tests with:

```sh
python -m unittest tests.test_repo_ci_dispatcher
```

Tests use a configured temporary provider that records the exact stdin
bytes.  They cover seven operations, zero/one/many stages, opaque
arguments, identity mismatch, malformed/duplicate JSON, bad config,
provider failures, semantic errors, and both entrypoints.  The POSIX
launcher test also checks that the committed file is executable.

No tests here certify a real hosted provider or protected-main
enforcement.  Those remain owned by #92-#94 and downstream tickets.
The dispatcher does not create pull requests, merge or publish tags.
