"""GitHub remote primitives for repo-host v1 mutations.

All writes use the authenticated GitHub CLI.  A request reservation is an
atomic Git tag creation.  Existing reservations are reconciled, never replayed
blindly.  Tags in this namespace are immutable protocol records.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess


class ProviderError(Exception):
  def __init__(self, code: str, message: str):
    super().__init__(message)
    self.code = code


def _json_call(method: str, route: str, payload: dict | None = None):
  args = ["gh", "api", "--method", method, route]
  if payload is not None:
    args.extend(["--input", "-"])
  try:
    p = subprocess.run(
      args, input=json.dumps(payload) if payload is not None else None,
      capture_output=True, text=True, check=False, timeout=30,
    )
  except (OSError, subprocess.TimeoutExpired) as exc:
    raise ProviderError("unknown_outcome" if method != "GET"
                        else "transport_failure", "GitHub request unavailable") from exc
  if p.returncode:
    # Do not expose untrusted provider diagnostics or potentially secret data.
    detail = p.stderr.lower()
    if "http 401" in detail:
      category = "unauthenticated"
    elif "http 403" in detail or "http 429" in detail:
      category = "rate_limited" if "rate limit" in detail else "unauthorized"
    elif "http 404" in detail:
      category = "not_found"
    elif "http 409" in detail or "http 422" in detail:
      category = "conflict"
    else:
      category = "transport_failure" if method == "GET" else "unknown_outcome"
    raise ProviderError(category, "GitHub request failed")
  try:
    return json.loads(p.stdout)
  except (TypeError, ValueError) as exc:
    raise ProviderError(
      "unknown_outcome" if method != "GET" else "invalid_response",
      "GitHub response is not valid JSON",
    ) from exc


def _object(value, keys: set[str] | None = None) -> dict:
  if not isinstance(value, dict):
    raise ProviderError("invalid_response", "GitHub response is not an object")
  if keys is not None and not keys <= set(value):
    raise ProviderError("invalid_response", "GitHub response missing fields")
  return value


def _number(value):
  if type(value) is not int or value <= 0:
    raise ProviderError("invalid_response", "invalid provider number")
  return value


def reservation_ref(request: dict) -> str:
  identity = (
    request["repository"] + "\0" + request["operation"] + "\0"
    + request["request_id"]
  )
  digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
  return "refs/tags/rwf-host-request-" + digest


def reservation_digest(request: dict) -> str:
  return hashlib.sha256(
    json.dumps(request, sort_keys=True, separators=(",", ":")).encode("utf-8")
  ).hexdigest()


class GitHubBackend:
  def __init__(self, repository: str):
    self.repository = repository
    self.prefix = "repos/" + repository + "/"

  def identity(self) -> dict:
    return _object(_json_call("GET", "user"), {"login"})

  def get(self, path: str):
    return _json_call("GET", self.prefix + path)

  def post(self, path: str, body: dict):
    return _json_call("POST", self.prefix + path, body)

  def patch(self, path: str, body: dict):
    return _json_call("PATCH", self.prefix + path, body)


  def set_draft(self, number: int, draft: bool) -> None:
    pr = self.pull(number)
    node_id = pr.get("node_id")
    if not isinstance(node_id, str) or not node_id:
      raise ProviderError("invalid_response", "missing GitHub PR node identity")
    mutation = (
      "convertPullRequestToDraft" if draft
      else "markPullRequestReadyForReview"
    )
    query = (
      "mutation($id:ID!){" + mutation
      + "(input:{pullRequestId:$id}){pullRequest{id,isDraft}}}"
    )
    response = _object(_json_call("POST", "graphql", {
      "query": query, "variables": {"id": node_id},
    }))
    if response.get("errors"):
      raise ProviderError("unknown_outcome", "GitHub draft change failed")
    data = _object(response.get("data"), {mutation})
    result = _object(data[mutation], {"pullRequest"})
    item = _object(result["pullRequest"], {"id", "isDraft"})
    if item["id"] != node_id or item["isDraft"] is not draft:
      raise ProviderError("unknown_outcome", "draft change not confirmed")

  def reserve(self, request: dict) -> bool:
    """Return true only for an atomically newly created reservation."""
    ref = reservation_ref(request)
    payload_digest = reservation_digest(request)
    repository = _object(self.get(""), {"default_branch"})
    default_branch = repository["default_branch"]
    if not isinstance(default_branch, str) or not re.fullmatch(
      r"[A-Za-z0-9._/-]+", default_branch
    ):
      raise ProviderError("invalid_response", "invalid default branch")
    base = _object(self.get("git/ref/heads/" + default_branch), {"object"})
    head = _object(base["object"], {"sha"})["sha"]
    if not re.fullmatch(r"[0-9a-f]{40}", str(head)):
      raise ProviderError("invalid_response", "invalid base commit")
    commit = _object(self.get("git/commits/" + head), {"tree"})
    tree = _object(commit["tree"], {"sha"})["sha"]
    record = _object(self.post("git/commits", {
      "message": "RWF-HOST-RESERVATION-V1 " + payload_digest,
      "tree": tree, "parents": [head],
    }), {"sha"})
    new_sha = record["sha"]
    if not re.fullmatch(r"[0-9a-f]{40}", str(new_sha)):
      raise ProviderError("invalid_response", "invalid reservation commit")
    try:
      self.post("git/refs", {"ref": ref, "sha": new_sha})
      return True
    except ProviderError:
      # A failed create is ambiguous.  Re-read the stable key, never
      # blindly perform the mutation.
      self.check_reservation(request)
      return False

  def check_reservation(self, request: dict) -> None:
    ref = reservation_ref(request)
    value = _object(self.get("git/ref/tags/" + ref.split("/")[-1]),
                    {"ref", "object"})
    if value["ref"] != ref:
      raise ProviderError("conflict", "reservation identity changed")
    sha = _object(value["object"], {"sha"})["sha"]
    record = _object(self.get("git/commits/" + sha), {"message"})
    expected = "RWF-HOST-RESERVATION-V1 " + reservation_digest(request)
    if record["message"] != expected:
      raise ProviderError("conflict", "request ID reused with changed inputs")

  def issue(self, number: int) -> dict:
    value = _object(self.get("issues/" + str(number)),
                    {"number", "title", "state"})
    if "pull_request" in value or _number(value["number"]) != number:
      raise ProviderError("invalid_response", "issue identity mismatch")
    if not isinstance(value["title"], str) or value["state"] not in (
      "open", "closed"
    ):
      raise ProviderError("invalid_response", "invalid issue state")
    return value

  def pull(self, number: int) -> dict:
    value = _object(self.get("pulls/" + str(number)),
                    {"number", "head", "base", "state", "draft"})
    if _number(value["number"]) != number:
      raise ProviderError("invalid_response", "PR number mismatch")
    if not isinstance(value["head"], dict) or not isinstance(value["base"], dict):
      raise ProviderError("invalid_response", "missing PR identities")
    if type(value["draft"]) is not bool or value["state"] not in (
      "open", "closed"
    ):
      raise ProviderError("invalid_response", "invalid PR lifecycle")
    return value
