# Stable Release Contract

This document extends the issue #1 RepoWorkflow design with the stable-release
contract required after an issue-qualified candidate has been accepted and its
source has been promoted to the repository's authoritative integration branch.

## Boundary

Development terminalization and stable release are distinct operations.

Development validation uses an issue-qualified version:

```text
X.Y.Z-issue.N.I
```

and may produce exactly one immutable terminal result tag:

```text
vX.Y.Z-issue.N.I
vX.Y.Z-issue.N.I-CI-FAIL
```

Stable release uses a plain semantic version already committed by the consumer:

```text
X.Y.Z
```

RepoWorkflow never edits a consumer's source/version files to manufacture a
stable version.  Stable-version selection and the source commit that reports it
remain repository-owned decisions.

## Stable candidate guard

Before stable validation or publication, RepoWorkflow must establish all of the
following from authoritative evidence:

1. the checkout is a clean, complete Git checkout;
2. the repository-owned version command reports exactly one plain `X.Y.Z`
   semantic version;
3. the checkout commit matches any explicitly supplied expected SHA;
4. the authoritative remote and configured integration branch are available;
5. the authoritative integration-branch head resolves to exactly the checkout
   commit;
6. `vX.Y.Z` does not already exist on the authoritative remote.

A stale local tag must not be treated as authoritative.  Inability to establish
remote branch or tag state is an error/INCOMPLETE condition, never an implicit
release authorization.

## Stable validation and publication

Stable validation reuses the same declared repository environments, generated
artifact safeguards, structured result records, and PASS / FAIL / INCOMPLETE
classification as development validation, but it uses the stable candidate
guard rather than `.ci/run-ci-request`.

Stable publication semantics are intentionally asymmetric with development
terminalization:

- complete required PASS => create/push annotated `vX.Y.Z` at the exact tested
  integration-branch commit;
- FAIL => no stable tag;
- INCOMPLETE => no stable tag.

A failed stable candidate therefore does not consume the version.  The
repository may correct `main` and re-run the same stable version until a PASS
establishes the immutable stable tag.

## GitHub adapter

The canonical GitHub adapter must distinguish two authoritative modes:

- `development`: explicit `.ci/run-ci-request` or manual development request;
- `stable`: a push whose exact candidate is the configured integration-branch
  head and whose repository-owned version command reports plain semantic
  versioning.

Both modes must use the same repository-owned environment validation commands,
artifact safeguards, exact candidate SHA, structured result aggregation, and
least-privilege publication boundary.  Only final tag semantics differ.

## RepoWorkflow repository bootstrap

RepoWorkflow itself cannot satisfy its consumer submodule invariant by mounting
itself at `RepoWorkflow/`.  Its own repository therefore uses a narrow bootstrap
self-CI workflow whose only responsibilities are:

- run `scripts/validate.py` on the exact commit;
- require the validation to leave the repository clean;
- on `main` only, after GREEN validation, publish the plain stable `VERSION`
  tag if and only if the tag does not already exist.

This bootstrap exception is specific to the RepoWorkflow repository.  Consumer
repositories must use the canonical adapter and shared engine rather than
copying the bootstrap workflow.
