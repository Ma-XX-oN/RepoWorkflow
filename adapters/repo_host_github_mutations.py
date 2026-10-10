"""Provider-backed ordinary mutations for the repo-host v1 contract."""
from __future__ import annotations

import hashlib
import json

from repo_host_github_provider import GitHubBackend, ProviderError
from repo_host_github_authority import authorize, verifier_command


def _marker(request: dict) -> str:
  value = (
    request["repository"] + "\0" + request["operation"] + "\0"
    + request["request_id"]
  )
  return "<!-- RWF-HOST-REQUEST-V1:" + hashlib.sha256(
    value.encode("utf-8")
  ).hexdigest() + " -->"


def _sha(value) -> str:
  if not isinstance(value, str) or len(value) != 40 or any(
    digit not in "0123456789abcdef" for digit in value
  ):
    raise ProviderError("invalid_response", "invalid GitHub SHA")
  return value


def _number(value) -> int:
  if type(value) is not int or value <= 0:
    raise ProviderError("invalid_response", "invalid GitHub number")
  return value


def _params(request: dict) -> dict:
  return request["parameters"]


def _issue_update(backend, request: dict, fresh: bool):
  p = _params(request)
  current = backend.issue(p["number"])
  changes = {k: p[k] for k in ("title", "state") if k in p}
  if all(current[key] == value for key, value in changes.items()):
    return "unchanged", {
      "number": p["number"], "title": current["title"],
      "state": current["state"],
    }
  if not fresh:
    raise ProviderError("unknown_outcome", "reserved update not reconciled")
  result = backend.patch("issues/" + str(p["number"]), changes)
  if not isinstance(result, dict):
    raise ProviderError("unknown_outcome", "invalid issue write result")
  observed = backend.issue(p["number"])
  if not all(observed[key] == value for key, value in changes.items()):
    raise ProviderError("unknown_outcome", "issue mutation not confirmed")
  return "applied", {
    "number": p["number"], "title": observed["title"],
    "state": observed["state"],
  }


def _issue_comment(backend, request: dict, fresh: bool):
  p = _params(request)
  number = p["number"]
  backend.issue(number)
  marker = _marker(request)
  # GitHub comment list is paginated: read every page, never infer absence
  # from only the first page.
  found = []
  page = 1
  while True:
    comments = backend.get(
      f"issues/{number}/comments?per_page=100&page={page}"
    )
    if not isinstance(comments, list):
      raise ProviderError("invalid_response", "invalid comments page")
    for comment in comments:
      if isinstance(comment, dict) and marker in str(comment.get("body", "")):
        found.append(comment)
    if len(comments) < 100:
      break
    page += 1
    if page > 1000:
      raise ProviderError("unknown_outcome", "comment scan exceeded bound")
  if len(found) > 1:
    raise ProviderError("conflict", "duplicate request comments")
  if found:
    item = found[0]
    actor = backend.identity().get("login")
    author = item.get("user")
    if not isinstance(author, dict) or author.get("login") != actor:
      raise ProviderError("conflict", "comment owner identity mismatch")
    comment_id = _number(item.get("id"))
    if item.get("body") != p["body"] + "\n" + marker:
      raise ProviderError("conflict", "comment request content mismatched")
    return "unchanged", {"number": number, "comment_id": str(comment_id)}
  if not fresh:
    raise ProviderError("unknown_outcome", "comment outcome unreconciled")
  result = backend.post("issues/" + str(number) + "/comments", {
    "body": p["body"] + "\n" + marker,
  })
  if not isinstance(result, dict):
    raise ProviderError("unknown_outcome", "invalid comment write response")
  comment_id = _number(result.get("id"))
  if result.get("body") != p["body"] + "\n" + marker:
    raise ProviderError("unknown_outcome", "comment write not verified")
  author = result.get("user")
  if not isinstance(author, dict) or (
    author.get("login") != backend.identity().get("login")
  ):
    raise ProviderError("unknown_outcome", "comment author not verified")
  return "applied", {"number": number, "comment_id": str(comment_id)}


def _branch(backend, ref: str) -> str:
  name = ref.removeprefix("refs/heads/")
  observed = backend.get("git/ref/heads/" + name)
  if not isinstance(observed, dict) or observed.get("ref") != ref:
    raise ProviderError("invalid_response", "branch ref mismatch")
  item = observed.get("object")
  if not isinstance(item, dict) or item.get("type") != "commit":
    raise ProviderError("invalid_response", "invalid branch object")
  return _sha(item.get("sha"))


def _pr_observed(backend, number: int, expected_sha: str | None = None):
  pr = backend.pull(number)
  head = pr["head"]
  base = pr["base"]
  sha = _sha(head.get("sha"))
  if expected_sha is not None and sha != expected_sha:
    raise ProviderError("conflict", "PR head changed")
  if not isinstance(base.get("ref"), str) or not base["ref"]:
    raise ProviderError("invalid_response", "invalid PR destination")
  return pr, sha


def _pr_create(backend, request: dict, fresh: bool):
  p = _params(request)
  source = p["source_ref"]
  target = p["target_ref"]
  expected = p["expected_source_sha"]
  if _branch(backend, source) != expected:
    raise ProviderError("conflict", "source head changed")
  _branch(backend, target)
  marker = _marker(request)
  source_short = source.removeprefix("refs/heads/")
  target_short = target.removeprefix("refs/heads/")
  # Scan even for newly reserved requests.  Deletion of a reservation ref
  # must not duplicate a previously created pull request.
  page = 1
  matches = []
  while True:
    items = backend.get("pulls?state=all&per_page=100&page=" + str(page))
    if not isinstance(items, list):
      raise ProviderError("invalid_response", "invalid PR list page")
    for item in items:
      if isinstance(item, dict) and item.get("body") == (
        p["body"] + "\n" + marker
      ):
        matches.append(item)
    if len(items) < 100:
      break
    page += 1
    if page > 1000:
      raise ProviderError("unknown_outcome", "PR scan exceeded bound")
  if len(matches) > 1:
    raise ProviderError("conflict", "multiple PRs match request identity")
  if matches:
    number = _number(matches[0].get("number"))
    author = matches[0].get("user")
    if not isinstance(author, dict) or (
      author.get("login") != backend.identity().get("login")
    ):
      raise ProviderError("conflict", "PR creator identity mismatch")
    observed, sha = _pr_observed(backend, number, expected)
    if observed["base"].get("ref") != target_short or (
      observed.get("draft") != p["draft"]
    ):
      raise ProviderError("conflict", "replayed PR identity differs")
    return "unchanged", {
      "number": number, "source_ref": source,
      "target_ref": target, "head_sha": sha, "draft": p["draft"],
    }
  if not fresh:
    raise ProviderError("unknown_outcome", "PR create outcome unreconciled")
  result = backend.post("pulls", {
    "head": source_short, "base": target_short,
    "title": p["title"], "body": p["body"] + "\n" + marker,
    "draft": p["draft"],
  })
  if not isinstance(result, dict):
    raise ProviderError("unknown_outcome", "invalid PR create response")
  number = _number(result.get("number"))
  observed, head_sha = _pr_observed(backend, number, expected)
  if observed["base"].get("ref") != target_short or (
    observed.get("draft") != p["draft"]
  ):
    raise ProviderError("unknown_outcome", "created PR identity mismatch")
  if observed.get("body") != p["body"] + "\n" + marker:
    raise ProviderError("unknown_outcome", "PR marker missing")
  author = observed.get("user")
  if not isinstance(author, dict) or (
    author.get("login") != backend.identity().get("login")
  ):
    raise ProviderError("unknown_outcome", "PR creator not verified")
  return "applied", {
    "number": number, "source_ref": source,
    "target_ref": target, "head_sha": head_sha, "draft": p["draft"],
  }


def _pr_update(backend, request: dict, fresh: bool):
  p = _params(request)
  number = p["number"]
  pr, sha = _pr_observed(backend, number, p["expected_head_sha"])
  changes = {
    k: p[k] for k in ("title", "body", "draft", "state", "target_ref")
    if k in p
  }
  values = dict(changes)
  if "target_ref" in values:
    values["base"] = values.pop("target_ref").removeprefix("refs/heads/")
  if all(pr.get(k) == v for k, v in values.items() if k != "base") and (
    "base" not in values or pr["base"]["ref"] == values["base"]
  ):
    return "unchanged", {
      "number": number, "head_sha": sha,
      "target_ref": "refs/heads/" + pr["base"]["ref"],
      "draft": pr["draft"], "state": pr["state"],
    }
  if not fresh:
    raise ProviderError("unknown_outcome", "PR update not reconciled")
  if "base" in values:
    _branch(backend, "refs/heads/" + values["base"])
  metadata = {key: value for key, value in values.items() if key != "draft"}
  if metadata:
    response = backend.patch("pulls/" + str(number), metadata)
    if not isinstance(response, dict):
      raise ProviderError("unknown_outcome", "invalid PR update response")
  if "draft" in values and values["draft"] != pr["draft"]:
    backend.set_draft(number, values["draft"])
  result, new_head = _pr_observed(backend, number, sha)
  if any(result.get(k) != v for k, v in values.items() if k != "base"):
    raise ProviderError("unknown_outcome", "PR update not confirmed")
  if "base" in values and result["base"]["ref"] != values["base"]:
    raise ProviderError("unknown_outcome", "PR destination not confirmed")
  return "applied", {
    "number": number, "head_sha": new_head,
    "target_ref": "refs/heads/" + result["base"]["ref"],
    "draft": result["draft"], "state": result["state"],
  }


def apply(request: dict, backend=None) -> tuple[str, dict]:
  operation = request["operation"]
  if operation in ("pull_request.merge", "check.publish"):
    raise ProviderError(
      "unsupported", "remote finalization/proof authority not available"
    )
  if operation not in {
    "issue.update", "issue.comment",
    "pull_request.create", "pull_request.update",
  }:
    raise ProviderError("unsupported", "unsupported host mutation")
  if backend is None:
    backend = GitHubBackend(request["repository"])
  authorize(request, backend)
  fresh = backend.reserve(request)
  if operation == "issue.update":
    return _issue_update(backend, request, fresh)
  if operation == "issue.comment":
    return _issue_comment(backend, request, fresh)
  if operation == "pull_request.create":
    return _pr_create(backend, request, fresh)
  return _pr_update(backend, request, fresh)


def capabilities() -> dict:
  available = verifier_command() is not None
  return {
    "issue.update": available,
    "issue.comment": available,
    "pull_request.create": available,
    "pull_request.update": available,
    "pull_request.merge": False,
    "check.publish": False,
  }
