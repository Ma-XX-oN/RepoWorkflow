"""Publish immutable destination-qualified READY PRELIM without queue markers."""
from dataclasses import dataclass
import re

_SHA = re.compile(r"[0-9a-f]{40}\Z")
_GUID = re.compile(
  r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z")
_DEST = re.compile(r"[A-Za-z0-9._/-]+\Z")


class ReadyPublicationError(RuntimeError):
  """PRELIM publication or authoritative readback is incomplete."""


@dataclass(frozen=True)
class PublishedReady:
  ref: str
  sha: str
  request_id: str


def publish_ready_prelim(
    *, ticket: int, destination: str, guid: str, candidate_sha: str,
    request_id: str, read_remote, create_if_absent,
    read_publication_record=None,
) -> PublishedReady:
  """Publish a prepared exact source SHA; never update an existing PRELIM.

  create_if_absent must be provider-idempotent under request_id and prove
  initial creation. An existing ref must not be adopted by comparing SHA only.
  """
  if type(ticket) is not int or ticket <= 0:
    raise ReadyPublicationError("ticket must be a positive issue ID")
  if (type(destination) is not str or _DEST.fullmatch(destination) is None
      or any(part in ("", ".", "..") for part in destination.split("/"))):
    raise ReadyPublicationError("invalid destination branch")
  if type(guid) is not str or _GUID.fullmatch(guid) is None:
    raise ReadyPublicationError("invalid attempt GUID")
  if type(candidate_sha) is not str or _SHA.fullmatch(candidate_sha) is None:
    raise ReadyPublicationError("invalid exact candidate SHA")
  if type(request_id) is not str or not request_id.strip():
    raise ReadyPublicationError("idempotent publication key is required")
  ref = f"refs/heads/PRELIM-issue-{ticket}/{destination}-{guid}"
  def exact_replay():
    if read_publication_record is None:
      return False
    record = read_publication_record(request_id)
    return (type(record) is dict
            and record == {
              "ref": ref, "sha": candidate_sha,
              "request_id": request_id, "status": "published",
            })

  existing = read_remote(ref)
  if existing is not None:
    if existing == candidate_sha and exact_replay():
      return PublishedReady(ref, candidate_sha, request_id)
    raise ReadyPublicationError("published PRELIM ref already exists")
  try:
    confirmed = create_if_absent(ref, candidate_sha, request_id)
  except Exception as error:
    # A lost reply is recoverable only with independent exact request-ID
    # evidence, not by matching a branch SHA alone.
    if read_remote(ref) == candidate_sha and exact_replay():
      return PublishedReady(ref, candidate_sha, request_id)
    raise ReadyPublicationError("publication outcome UNKNOWN; reconcile") from error
  if confirmed is not True:
    raise ReadyPublicationError("provider did not certify initial ref creation")
  if read_remote(ref) != candidate_sha:
    raise ReadyPublicationError("published PRELIM identity readback differs")
  return PublishedReady(ref, candidate_sha, request_id)


def create_ready_ref_git(root, remote, ref, sha, request_id):
  """Atomically create a READY PRELIM ref only when remote has no such ref.

  A plain non-force push is insufficient: it might advance an existing ref.
  The empty expected-oid lease is the create-only condition.
  """
  import subprocess
  from pathlib import Path

  valid_ref = (type(ref) is str and re.fullmatch(
    r"refs/heads/PRELIM-issue-[1-9][0-9]*/"
    r"[A-Za-z0-9._/-]+-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}",
    ref) is not None)
  if valid_ref:
    destination = ref.split("/", 3)[3][:-37]
    valid_ref = all(part not in ("", ".", "..")
                    for part in destination.split("/"))
  if (not valid_ref
      or type(sha) is not str or _SHA.fullmatch(sha) is None
      or type(request_id) is not str or not request_id
      or type(remote) is not str or not remote or remote.startswith("-")):
    raise ReadyPublicationError("invalid create-only PRELIM request")
  root = Path(root)
  def run(*args):
    try:
      return subprocess.run(["git", "-C", str(root), *args],
        capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
      raise ReadyPublicationError("PRELIM creation outcome UNKNOWN") from error
  if run("cat-file", "-e", sha + "^{commit}").returncode:
    raise ReadyPublicationError("PRELIM candidate commit is missing")
  result = run("push", "--porcelain",
    "--force-with-lease=" + ref + ":", remote, sha + ":" + ref)
  if result.returncode:
    raise ReadyPublicationError("PRELIM create-only push rejected or UNKNOWN")
  readback = run("ls-remote", "--heads", remote, ref)
  if readback.returncode:
    raise ReadyPublicationError("PRELIM create-only readback UNKNOWN")
  fields = readback.stdout.strip().split()
  if len(fields) != 2 or fields[0] != sha or fields[1] != ref:
    raise ReadyPublicationError("PRELIM published ref differs on readback")
  return True
