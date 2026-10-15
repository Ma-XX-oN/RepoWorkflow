"""Strict, versioned identity checks for persisted PRELIM attempts."""
from __future__ import annotations

import re
import uuid

SHA = re.compile(r"[0-9a-f]{40}\Z")
ISSUE = re.compile(r"[1-9][0-9]*\Z")
VERSION = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\."
                     r"(?:0|[1-9][0-9]*)\Z")
FIELDS = frozenset({
  "attempt", "issue", "branch", "source_ref", "source_sha",
  "base_sha", "lifecycle_revision", "bump", "state",
  "candidate_sha", "proposed_version",
})


class PrelimIdentityError(ValueError):
  pass


def validate_attempt(value: dict) -> None:
  if not isinstance(value, dict) or set(value) != FIELDS:
    raise PrelimIdentityError("PRELIM attempt schema mismatch")
  attempt = value["attempt"]
  try:
    canonical = str(uuid.UUID(attempt))
  except (ValueError, AttributeError, TypeError) as exc:
    raise PrelimIdentityError("PRELIM attempt GUID is invalid") from exc
  if attempt != canonical:
    raise PrelimIdentityError("PRELIM attempt GUID is not canonical")
  issue = value["issue"]
  if not isinstance(issue, str) or not ISSUE.fullmatch(issue):
    raise PrelimIdentityError("PRELIM issue is invalid")
  if value["branch"] != f"prelim-main-{attempt}":
    raise PrelimIdentityError("PRELIM branch identity is invalid")
  source_ref = value["source_ref"]
  if (not isinstance(source_ref, str) or re.fullmatch(
      rf"refs/heads/issue-{issue}(?:-[A-Za-z0-9._/-]+)?", source_ref
  ) is None):
    raise PrelimIdentityError("PRELIM accepted source identity is invalid")
  for field in ("source_sha", "base_sha"):
    if not isinstance(value[field], str) or not SHA.fullmatch(value[field]):
      raise PrelimIdentityError(f"PRELIM {field} is invalid")
  revision = value["lifecycle_revision"]
  if type(revision) is not int or revision < 0:
    raise PrelimIdentityError("PRELIM lifecycle revision is invalid")
  if value["bump"] not in ("patch", "minor"):
    raise PrelimIdentityError("PRELIM version intent is invalid")
  state = value["state"]
  if state not in ("prepared", "versioned", "conflict", "ready"):
    raise PrelimIdentityError("PRELIM attempt state is invalid")
  version = value["proposed_version"]
  candidate = value["candidate_sha"]
  if state == "prepared":
    if version is not None or candidate is not None:
      raise PrelimIdentityError("prepared PRELIM has published identity")
  elif (not isinstance(version, str)
        or not VERSION.fullmatch(version)):
    raise PrelimIdentityError("PRELIM proposed version is invalid")
  if state == "ready":
    if not isinstance(candidate, str) or not SHA.fullmatch(candidate):
      raise PrelimIdentityError("ready PRELIM candidate SHA is invalid")
  elif candidate is not None:
    raise PrelimIdentityError("unready PRELIM has candidate identity")
