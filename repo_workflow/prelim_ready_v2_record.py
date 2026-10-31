"""Destination-qualified PRELIM preparation identity, never a READY assertion."""
from dataclasses import dataclass
import re
import uuid

from .prelim_attempt_lock import PrelimError
from .prelim_identity import SHA, VERSION


_ISSUE = re.compile(r"[1-9][0-9]*\Z")
_DEST = re.compile(r"[A-Za-z0-9._/-]+\Z")
_FIELDS = frozenset({
  "guid", "issue", "destination", "source_ref", "source_sha",
  "base_sha", "lifecycle_revision", "bump", "state",
  "candidate_sha", "proposed_version",
})
_STATES = {"prepared", "versioned", "conflict", "constructed"}


@dataclass(frozen=True)
class PreparedCandidate:
  guid: str
  issue: str
  destination: str
  source_sha: str
  base_sha: str
  candidate_sha: str
  proposed_version: str


def preparation_key(guid: str) -> str:
  return "prelim/v2-prepared/" + guid


def preparation_ref(guid: str) -> str:
  return "refs/heads/prelim-v2-prepared/" + guid


def validate_preparation(value: dict) -> None:
  if type(value) is not dict or set(value) != _FIELDS:
    raise PrelimError("destination PRELIM state schema invalid")
  try:
    canonical = str(uuid.UUID(value["guid"]))
  except (ValueError, TypeError, AttributeError) as error:
    raise PrelimError("preparation GUID invalid") from error
  if (canonical != value["guid"]
      or type(value["issue"]) is not str
      or _ISSUE.fullmatch(value["issue"]) is None
      or type(value["destination"]) is not str
      or _DEST.fullmatch(value["destination"]) is None
      or any(part in ("", ".", "..")
             for part in value["destination"].split("/"))
      or type(value["source_ref"]) is not str
      or re.fullmatch(
        rf"refs/heads/issue-{value['issue']}(?:-[A-Za-z0-9._/-]+)?",
        value["source_ref"]) is None):
    raise PrelimError("destination PRELIM scope invalid")
  if any(type(value[k]) is not str or SHA.fullmatch(value[k]) is None
         for k in ("source_sha", "base_sha")):
    raise PrelimError("destination PRELIM SHA malformed")
  if (type(value["lifecycle_revision"]) is not int
      or value["lifecycle_revision"] < 0
      or value["bump"] not in ("patch", "minor")
      or value["state"] not in _STATES):
    raise PrelimError("destination PRELIM lifecycle invalid")
  if value["state"] == "prepared":
    if value["proposed_version"] is not None:
      raise PrelimError("unversioned candidate has a version")
  elif (type(value["proposed_version"]) is not str
        or VERSION.fullmatch(value["proposed_version"]) is None):
    raise PrelimError("prepared candidate version invalid")
  if value["state"] == "constructed":
    sha = value["candidate_sha"]
    if type(sha) is not str or SHA.fullmatch(sha) is None:
      raise PrelimError("constructed candidate SHA missing")
  elif value["candidate_sha"] is not None:
    raise PrelimError("incomplete construction has candidate SHA")


def prepared_snapshot(value: dict) -> PreparedCandidate:
  validate_preparation(value)
  if value["state"] != "constructed":
    raise PrelimError("candidate is not constructed")
  return PreparedCandidate(
    value["guid"], value["issue"], value["destination"],
    value["source_sha"], value["base_sha"], value["candidate_sha"],
    value["proposed_version"],
  )
