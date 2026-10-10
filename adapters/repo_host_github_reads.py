"""Read-only GitHub facts used before privileged host mutation.

No method in this module changes provider state.  Verification of an
expected SHA is not an atomic remote mutation or authorization decision.
"""
from __future__ import annotations

import json
import re
import subprocess


_SHA = re.compile(r"[0-9a-f]{40}\Z")


class ProviderReadError(RuntimeError):
  pass


def _sha(value: object, field: str) -> str:
  if not isinstance(value, str) or not _SHA.fullmatch(value):
    raise ProviderReadError(f"invalid GitHub {field}")
  return value


def _positive(value: object, field: str) -> int:
  if type(value) is not int or value <= 0:
    raise ProviderReadError(f"invalid GitHub {field}")
  return value


def _text(value: object, field: str) -> str:
  if not isinstance(value, str) or not value:
    raise ProviderReadError(f"invalid GitHub {field}")
  return value


def api_get(repository: str, route: str) -> dict:
  if not re.fullmatch(r"[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+", repository):
    raise ProviderReadError("invalid repository")
  if any(part in {".", ".."} for part in repository.split("/")):
    raise ProviderReadError("invalid repository component")
  if not route.startswith("repos/" + repository + "/"):
    raise ProviderReadError("invalid repository-scoped route")
  result = subprocess.run(
    ["gh", "api", "--method", "GET", route],
    text=True, capture_output=True, check=False,
  )
  if result.returncode:
    raise ProviderReadError("GitHub provider read failed")
  try:
    value = json.loads(result.stdout)
  except json.JSONDecodeError as exc:
    raise ProviderReadError("malformed GitHub provider JSON") from exc
  if not isinstance(value, dict):
    raise ProviderReadError("invalid GitHub provider object")
  return value


def issue_get(repository: str, number: int) -> dict:
  _positive(number, "requested issue number")
  value = api_get(repository, f"repos/{repository}/issues/{number}")
  if "pull_request" in value:
    raise ProviderReadError("GitHub number denotes a pull request")
  returned = _positive(value.get("number"), "issue number")
  if returned != number:
    raise ProviderReadError("GitHub issue identity mismatch")
  title = _text(value.get("title"), "issue title")
  state = value.get("state")
  if state not in ("open", "closed"):
    raise ProviderReadError("invalid GitHub issue state")
  return {"number": returned, "title": title, "state": state}


def pull_request_get(repository: str, number: int) -> dict:
  _positive(number, "requested PR number")
  value = api_get(repository, f"repos/{repository}/pulls/{number}")
  returned = _positive(value.get("number"), "PR number")
  if returned != number:
    raise ProviderReadError("GitHub PR identity mismatch")
  head = value.get("head")
  base = value.get("base")
  if not isinstance(head, dict) or not isinstance(base, dict):
    raise ProviderReadError("missing GitHub PR refs")
  state = value.get("state")
  if state not in ("open", "closed") or type(value.get("draft")) is not bool:
    raise ProviderReadError("invalid GitHub PR state")
  return {
    "number": returned,
    "head_sha": _sha(head.get("sha"), "PR head SHA"),
    "target_ref": "refs/heads/" + _text(base.get("ref"), "PR base ref"),
    "destination_sha": _sha(base.get("sha"), "destination SHA"),
    "draft": value["draft"],
    "state": state,
  }


def branch_head(repository: str, name: str) -> str:
  if not isinstance(name, str) or not re.fullmatch(
    r"[A-Za-z0-9._/-]+", name
  ) or name.startswith("/") or ".." in name or "//" in name:
    raise ProviderReadError("invalid GitHub branch ref")
  route = f"repos/{repository}/git/ref/heads/{name}"
  value = api_get(repository, route)
  ref = value.get("ref")
  object_value = value.get("object")
  if ref != "refs/heads/" + name or not isinstance(object_value, dict):
    raise ProviderReadError("GitHub branch identity mismatch")
  if object_value.get("type") != "commit":
    raise ProviderReadError("GitHub branch does not point to commit")
  return _sha(object_value.get("sha"), "branch SHA")
