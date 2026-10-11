"""Fail-closed GitHub exact-candidate status publisher (#637)."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

CONTEXT = "repo-workflow/exact-candidate"
_SHA = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
_REF = re.compile(r"[A-Za-z0-9_./-]+\Z")


class PublishError(RuntimeError):
  pass


@dataclass(frozen=True)
class VerifiedDecision:
  candidate: str
  base: str
  evidence_id: str
  issuer: str
  allowed: bool


def _identity(repository, candidate, base, branch):
  if not isinstance(repository, str) or not _REPO.fullmatch(repository):
    raise PublishError("invalid repository")
  if any(not isinstance(s, str) or not _SHA.fullmatch(s)
         for s in (candidate, base)) or len(candidate) != len(base):
    raise PublishError("invalid candidate or base")
  if (not isinstance(branch, str) or not _REF.fullmatch(branch)
      or branch.startswith(("/", "-")) or branch.endswith("/")
      or "//" in branch or any(p in (".", "..") for p in branch.split("/"))):
    raise PublishError("invalid destination ref")


def _api(repository, token, path, *, payload=None):
  if not isinstance(token, str) or not token.strip():
    raise PublishError("missing authenticated publisher credentials")
  headers = {
    "Authorization": "Bearer " + token,
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
  }
  data = None
  if payload is not None:
    headers["Content-Type"] = "application/json"
    data = json.dumps(payload).encode("utf-8")
  request = Request(
    "https://api.github.com/repos/" + repository + path,
    data=data, headers=headers, method="POST" if data is not None else "GET",
  )
  try:
    with urlopen(request, timeout=15) as response:
      result = json.load(response)
  except (HTTPError, URLError, ValueError, OSError) as exc:
    raise PublishError("GitHub unavailable or denied") from exc
  if not isinstance(result, (dict, list)):
    raise PublishError("malformed GitHub response")
  return result


def publish(
  repository, candidate, expected_base, destination, token, *,
  evidence, verifier, provider=None,
):
  """Require independent evidence verification; never trust a JSON PASS.

  The verifier authenticates #548 completed evidence and performs the #104
  exact-candidate decision. This standalone module does not provide an
  untrusted external API for asserting VerifiedDecision.
  """
  _identity(repository, candidate, expected_base, destination)
  if not callable(verifier):
    raise PublishError("missing authoritative evidence verifier")
  if provider is None and (not isinstance(token, str) or not token.strip()):
    raise PublishError("missing authenticated publisher credentials")
  request = provider or (lambda path, payload=None:
                         _api(repository, token, path, payload=payload))

  def base_sha():
    response = request("/branches/" + quote(destination, safe=""))
    try:
      sha = response["commit"]["sha"]
    except (KeyError, TypeError) as exc:
      raise PublishError("invalid branch response") from exc
    if not isinstance(sha, str) or not _SHA.fullmatch(sha):
      raise PublishError("invalid provider base SHA")
    return sha

  post_attempted = False
  try:
    first = base_sha()
    if first != expected_base:
      raise PublishError("stale destination base")
    decision = verifier(evidence, candidate, expected_base)
    if (type(decision) is not VerifiedDecision
        or decision.candidate != candidate or decision.base != expected_base
        or decision.allowed is not True
        or not isinstance(decision.evidence_id, str)
        or not decision.evidence_id.strip()
        or not isinstance(decision.issuer, str)
        or not decision.issuer.strip()):
      raise PublishError("incomplete, stale or unauthenticated evidence")
    if base_sha() != first:
      raise PublishError("destination changed during validation")
    previous = request("/commits/" + candidate + "/statuses")
    if not isinstance(previous, list):
      raise PublishError("cannot verify existing status history")
    description = "verified " + decision.evidence_id[:70]
    for prior in previous:
      if (not isinstance(prior, dict)
          or not isinstance(prior.get("context"), str)):
        raise PublishError("malformed status history")
      if (prior["context"] == CONTEXT
          and prior.get("description") == description):
        raise PublishError("evidence replay")
    # GitHub's status API has no compare-and-swap operation. Atomically
    # claim one durable per-candidate ref before any success publication.
    # Conflicting writers cannot both create the same ref. Retain the ref
    # after errors so ambiguous attempts fail closed instead of racing.
    lock_ref = "refs/heads/rwf-exact-check-lock/" + candidate
    acquired = request("/git/refs", {
      "ref": lock_ref, "sha": candidate,
    })
    if (not isinstance(acquired, dict)
        or acquired.get("ref") != lock_ref
        or acquired.get("object", {}).get("sha") != candidate):
      raise PublishError("candidate publication lock unverified")
    saved_lock = request("/git/ref/heads/rwf-exact-check-lock/" + candidate)
    if (not isinstance(saved_lock, dict)
        or saved_lock.get("ref") != lock_ref
        or saved_lock.get("object", {}).get("sha") != candidate):
      raise PublishError("candidate publication lock not persisted")
    if base_sha() != first:
      raise PublishError("destination changed after lock acquisition")
    post_attempted = True
    result = request("/statuses/" + candidate, {
      "state": "success", "context": CONTEXT,
      "description": description,
    })
    if (not isinstance(result, dict) or result.get("context") != CONTEXT
        or result.get("state") != "success"
        or type(result.get("id")) is not int
        or not isinstance(result.get("creator"), dict)
        or result["creator"].get("login") != decision.issuer):
      raise PublishError("publication response not authenticated")
    observed = request("/commits/" + candidate + "/statuses")
    if not isinstance(observed, list):
      raise PublishError("invalid status readback")
    matches = [s for s in observed if isinstance(s, dict)
               and s.get("context") == CONTEXT]
    if (not matches or matches[0].get("id") != result["id"]
        or matches[0].get("state") != "success"
        or matches[0].get("creator", {}).get("login") !=
           result["creator"]["login"]):
      raise PublishError("status readback mismatch")
    if base_sha() != first:
      raise PublishError("destination changed after publication")
    return {"sha": candidate, "base": first, "status_id": result["id"],
            "issuer": result["creator"]["login"], "context": CONTEXT}
  except (PublishError, ValueError, TypeError, KeyError, OSError,
          RuntimeError) as exc:
    if post_attempted:
      # A status POST has no atomic rollback. Immediately supersede any
      # ambiguous or invalid success and verify failure persisted.
      try:
        revoked = request("/statuses/" + candidate, {
          "state": "failure", "context": CONTEXT,
          "description": "revoked: exact-candidate publication failed",
        })
        history = request("/commits/" + candidate + "/statuses")
        if (not isinstance(revoked, dict)
            or revoked.get("state") != "failure"
            or revoked.get("context") != CONTEXT
            or not isinstance(history, list) or not history
            or history[0].get("id") != revoked.get("id")
            or history[0].get("state") != "failure"):
          raise PublishError("revocation not observed")
      except (PublishError, ValueError, TypeError, KeyError, OSError,
              RuntimeError) as revoke_error:
        raise PublishError(
          "publication failed; required failure revocation unverified"
        ) from revoke_error
    if isinstance(exc, PublishError):
      raise
    raise PublishError("provider or verifier unavailable") from exc


def publish_from_store(
  repository, candidate, expected_base, source, destination, token, *,
  store, requirement_manifest, record_ids, version,
  coverage_evaluator, provider_verifier,
):
  """Production entrypoint using the completed #104/#548 evidence interface.

  The invoking runner MUST obtain the complete requirements manifest from its
  protected authoritative configuration; the source/runner are trusted under
  #548's current trusted-publisher assumption. No caller-supplied PASS accepted.
  """
  if not callable(provider_verifier) or not callable(coverage_evaluator):
    raise PublishError("missing trusted evidence verification")
  if not isinstance(record_ids, (list, tuple)) or not record_ids:
    raise PublishError("missing completed evidence records")
  from .github_host_facts import decide_with_verified_sources

  def verify(_evidence, sha, base):
    allowed, reasons = decide_with_verified_sources(
      store, requirement_manifest, record_ids,
      candidate=sha, version=version, source=source,
      destination=destination, recorded_base=base, repository=repository,
      token=token, coverage_evaluator=coverage_evaluator,
      provider_verifier=provider_verifier,
    )
    if not allowed:
      raise PublishError("ineligible verified evidence: " + ", ".join(reasons))
    # A published run identity must be bound to the authenticated observations.
    evidence_id = ",".join(record_ids)
    if len(evidence_id) > 128:
      raise PublishError("evidence identity exceeds check description capacity")
    return VerifiedDecision(sha, base, evidence_id,
                            "github-actions[bot]", True)

  return publish(
    repository, candidate, expected_base, destination, token,
    evidence=record_ids, verifier=verify,
  )
