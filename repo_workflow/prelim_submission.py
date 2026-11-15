"""Immutable submission provenance; this record never asserts a test PASS."""
import json
from pathlib import Path
import re

from .prelim_queue import parse_ready_prelim
from .git import git


PREFIX = "RWF-PRELIM-SUBMISSION-V1 "
FIELDS = {"repository", "guid", "prelim_ref", "source_sha", "candidate_sha",
          "parent_sha", "predecessor_ref", "inputs_sha256", "release"}


class SubmissionError(ValueError):
  """Submission source, generation or provider identity is unverified."""


def validate_submission(record: dict, *, repository: str, guid: str) -> None:
  """Validate provenance without treating a completion submission as test proof.

  Parameters
  ----------
  record : dict
      Immutable submission metadata.
  repository, guid : str
      Independently observed repository and submission identity.

  Returns
  -------
  None
      Raises SubmissionError on malformed or mismatched identity.
  """
  if (type(repository) is not str or re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) is None
      or type(record) is not dict or set(record) != FIELDS
      or record["repository"] != repository or record["guid"] != guid
      or type(record["release"]) is not str
      or record["release"] not in {"patch", "minor", "major"}):
    raise SubmissionError("submission envelope differs from provider identity")
  for field in ("source_sha", "candidate_sha", "parent_sha"):
    if type(record[field]) is not str or re.fullmatch(r"[0-9a-f]{40}", record[field]) is None:
      raise SubmissionError("submission needs exact source and parent SHAs")
  if (type(record["inputs_sha256"]) is not str
      or re.fullmatch(r"[0-9a-f]{64}", record["inputs_sha256"]) is None):
    raise SubmissionError("submission needs an exact relevant-input digest")
  try:
    ready = parse_ready_prelim(record["prelim_ref"], record["candidate_sha"])
    predecessor = (parse_ready_prelim(record["predecessor_ref"], record["candidate_sha"])
                   if record["predecessor_ref"] is not None else None)
  except (ValueError, TypeError) as error:
    raise SubmissionError("invalid submission ref identity") from error
  if ready is None or ready.guid != guid:
    raise SubmissionError("submission ref differs from GUID")
  if record["predecessor_ref"] is not None and (
      predecessor is None or predecessor.ref == ready.ref
      or (predecessor.umbrella, predecessor.destination)
         != (ready.umbrella, ready.destination)):
    raise SubmissionError("predecessor must be another generation of the same issue and parent")


def submission_message(record: dict) -> str:
  """Encode the sole canonical metadata representation.

  Parameters
  ----------
  record : dict
      Previously validated submission.

  Returns
  -------
  str
      Canonical commit message, independent of Git commit timestamps.
  """
  return PREFIX + json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False)


def submission_ref(guid: str) -> str:
  """Locate a submission receipt independently of mutable queue ordering.

  Parameters
  ----------
  guid : str
      Canonical UUID of the submission.

  Returns
  -------
  str
      Receipt tag ref; a receipt does not grant merge authority.
  """
  if type(guid) is not str or re.fullmatch(
      r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", guid) is None:
    raise SubmissionError("invalid submission GUID")
  return "refs/tags/rwf-prelim-submission-v1-" + guid


def decode_submission(message: str, *, repository: str, guid: str) -> dict:
  """Decode a provider receipt, rejecting noncanonical or ambiguous JSON.

  Parameters
  ----------
  message : str
      Exact message from the provider's receipt commit.
  repository, guid : str
      Independently observed scope.

  Returns
  -------
  dict
      Validated provenance, never a certification result.
  """
  if not isinstance(message, str) or not message.startswith(PREFIX):
    raise SubmissionError("submission receipt signature missing")
  message = message.removesuffix("\n")
  try:
    record = json.loads(message[len(PREFIX):])
    validate_submission(record, repository=repository, guid=guid)
    if submission_message(record) != message:
      raise SubmissionError("noncanonical submission receipt")
  except (ValueError, TypeError, RecursionError) as error:
    raise SubmissionError("invalid canonical submission receipt") from error
  return record


def publish_submission(root: Path, record: dict, *, remote: str, push: bool = True):
  """Create one immutable PRELIM and its provenance in an atomic publication.

  Parameters
  ----------
  root : Path
      Repository containing the exact prepared source and candidate objects.
  record : dict
      Submission provenance, with no asserted PASS or merge authorization.
  remote : str
      Independently configured authoritative repository remote.
  push : bool
      Publish remotely, or create only local immutable refs.

  Returns
  -------
  ReadyPrelim
      Submission whose exact physical refs were read back. Uncertain writes
      raise SubmissionError and retain the original local receipt for recovery.
  """
  if type(record) is not dict:
    raise SubmissionError("submission record required")
  validate_submission(record, repository=record.get("repository"), guid=record.get("guid"))
  receipt_ref = submission_ref(record["guid"])
  ready_ref, candidate = record["prelim_ref"], record["candidate_sha"]
  for ancestor in (record["source_sha"], record["parent_sha"]):
    if git(root, "merge-base", "--is-ancestor", ancestor, candidate, check=False).returncode:
      raise SubmissionError("prepared PRELIM does not include its source and parent")

  def inventory():
    """Read both physical identities from the configured provider."""
    output = git(root, "ls-remote", "--refs", remote, ready_ref, receipt_ref).stdout
    observed = {}
    for line in output.splitlines():
      parts = line.split("\t")
      if (len(parts) != 2 or parts[1] not in {ready_ref, receipt_ref}
          or re.fullmatch(r"[0-9a-f]{40}", parts[0]) is None or parts[1] in observed):
        raise SubmissionError("ambiguous remote submission refs")
      observed[parts[1]] = parts[0]
    return observed

  remote_refs = inventory() if push else {}
  if ready_ref in remote_refs and (remote_refs[ready_ref] != candidate or receipt_ref not in remote_refs):
    raise SubmissionError("PRELIM already exists with different or missing provenance")
  if receipt_ref in remote_refs:
    git(root, "fetch", "--no-tags", remote, receipt_ref)
  local = git(root, "rev-parse", "--verify", "--quiet", receipt_ref, check=False)
  if local.returncode not in (0, 1):
    raise SubmissionError("local submission receipt unavailable")
  receipt = local.stdout.strip() if local.returncode == 0 else remote_refs.get(receipt_ref)
  if receipt is not None:
    message = git(root, "show", "-s", "--format=%B", receipt).stdout.removesuffix("\n")
    saved = decode_submission(message, repository=record["repository"], guid=record["guid"])
    parents = git(root, "rev-list", "--parents", "-n", "1", receipt).stdout.split()
    tree = git(root, "rev-parse", receipt + "^{tree}").stdout.strip()
    if (saved != record or parents != [receipt, candidate]
        or tree != git(root, "rev-parse", candidate + "^{tree}").stdout.strip()
        or receipt_ref in remote_refs and remote_refs[receipt_ref] != receipt):
      raise SubmissionError("immutable submission receipt differs; reconcile")
  else:
    tree = git(root, "rev-parse", candidate + "^{tree}").stdout.strip()
    receipt = git(root, "commit-tree", tree, "-p", candidate,
                  "-m", submission_message(record)).stdout.strip()
  zero = "0" * 40
  for ref, sha in ((receipt_ref, receipt), (ready_ref, candidate)):
    current = git(root, "rev-parse", "--verify", "--quiet", ref, check=False)
    if current.returncode == 0:
      if current.stdout.strip() != sha:
        raise SubmissionError("immutable local submission ref differs")
    elif current.returncode == 1:
      git(root, "update-ref", ref, sha, zero)
    else:
      raise SubmissionError("local submission ref read UNKNOWN")
  if push:
    result = git(root, "push", "--atomic",
                 "--force-with-lease=" + ready_ref + ":" + remote_refs.get(ready_ref, ""),
                 "--force-with-lease=" + receipt_ref + ":" + remote_refs.get(receipt_ref, ""),
                 remote, candidate + ":" + ready_ref, receipt + ":" + receipt_ref, check=False)
    observed = inventory()
    if observed != {ready_ref: candidate, receipt_ref: receipt}:
      raise SubmissionError("submission publication UNKNOWN; reconcile provider refs")
    if result.returncode:
      # A lost response is reconciled only by exact readback of both objects.
      return parse_ready_prelim(ready_ref, candidate)
  return parse_ready_prelim(ready_ref, candidate)
