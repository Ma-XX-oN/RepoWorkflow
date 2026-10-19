"""Provider-authoritative per-destination lease using a CAS-only Git tag.

This ref is coordination state, never READY admission or a queue.  Only the
expected-old ref transaction advances its generation; REST ref PATCH is not CAS.
"""
import hashlib
import json
from pathlib import Path
import re
import subprocess


class LeaseProviderError(RuntimeError):
  """Destination lease state, identity or atomic publication is unverified."""


_SHA = re.compile(r"[0-9a-f]{40}\Z")
_GUID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z")
_DEST = re.compile(r"[A-Za-z0-9._/-]+\Z")
_PREFIX = "RWF-INTEGRATION-LEASE-V2 "
_FIELDS = {"repository", "destination", "generation", "holder", "guid",
           "request_id"}


def _ref(repository, destination):
  if (type(repository) is not str
      or re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) is None
      or type(destination) is not str or _DEST.fullmatch(destination) is None
      or any(p in ("", ".", "..") for p in destination.split("/"))):
    raise LeaseProviderError("invalid destination lease scope")
  digest = hashlib.sha256((repository + "\0" + destination).encode()).hexdigest()
  return "refs/tags/rwf-integration-lease-v2-" + digest


def _validate(value, repository, destination):
  if type(value) is not dict or set(value) != _FIELDS:
    raise LeaseProviderError("lease record schema invalid")
  if value["repository"] != repository or value["destination"] != destination:
    raise LeaseProviderError("lease record scope differs")
  if type(value["generation"]) is not int or value["generation"] < 1:
    raise LeaseProviderError("lease record generation invalid")
  if ((value["holder"] is None) != (value["guid"] is None)
      or (value["holder"] is not None and (
        type(value["holder"]) is not str or not value["holder"].strip()))
      or (value["guid"] is not None and (
        type(value["guid"]) is not str or not _GUID.fullmatch(value["guid"])))):
    raise LeaseProviderError("lease holder identity invalid")
  if (type(value["request_id"]) is not str
      or re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", value["request_id"]) is None):
    raise LeaseProviderError("lease request identity invalid")


def _read(backend, destination):
  repository = backend.repository
  ref = _ref(repository, destination)
  try:
    response = backend.get("git/ref/tags/" + ref.rsplit("/", 1)[1])
  except Exception as error:
    if getattr(error, "code", None) == "not_found":
      return None, None
    raise LeaseProviderError("provider lease read UNKNOWN") from error
  if (type(response) is not dict or response.get("ref") != ref
      or type(response.get("object")) is not dict):
    raise LeaseProviderError("provider lease ref malformed")
  sha = response["object"].get("sha")
  if type(sha) is not str or _SHA.fullmatch(sha) is None:
    raise LeaseProviderError("provider lease object malformed")
  try:
    commit = backend.get("git/commits/" + sha)
    message = commit["message"]
    if type(message) is not str or not message.startswith(_PREFIX):
      raise ValueError("lease message")
    value = json.loads(message[len(_PREFIX):])
    _validate(value, repository, destination)
    if json.dumps(value, sort_keys=True, separators=(",", ":")) != message[len(_PREFIX):]:
      raise ValueError("noncanonical lease")
  except Exception as error:
    raise LeaseProviderError("provider lease record invalid") from error
  return sha, value


def read_lease(backend, destination):
  _, value = _read(backend, destination)
  return {"destination": destination,
          "generation": value["generation"] if value else 0,
          "holder": value["holder"] if value else None,
          "guid": value["guid"] if value else None}


def _git(root, *args):
  try:
    result = subprocess.run(["git", "-C", str(root), *args], check=False,
      capture_output=True, text=True, timeout=30)
  except (OSError, subprocess.TimeoutExpired) as error:
    raise LeaseProviderError("Git CAS transport UNKNOWN") from error
  return result


def _remote_scope(root, remote, backend):
  """Resolve the exact provider-authenticated URL, not a mutable Git alias."""
  if type(remote) is not str or not remote or remote.startswith("-"):
    raise LeaseProviderError("invalid configured remote")
  try:
    details = backend.get("")
  except Exception as error:
    raise LeaseProviderError("provider repository identity unavailable") from error
  repository = backend.repository
  if (type(details) is not dict or details.get("full_name") != repository):
    raise LeaseProviderError("provider repository identity mismatch")
  approved = {
    url for url in (details.get("clone_url"), details.get("ssh_url"))
    if type(url) is str and url and not any(
      ch in url for ch in ("\\n", "\\r", "\\x00"))
  }
  if not approved:
    raise LeaseProviderError("provider repository endpoint unavailable")
  fetch = _git(root, "remote", "get-url", remote)
  push = _git(root, "remote", "get-url", "--push", remote)
  if (fetch.returncode or push.returncode
      or fetch.stdout.strip() != push.stdout.strip()
      or fetch.stdout.strip() not in approved):
    raise LeaseProviderError("configured Git remote repository differs")
  return fetch.stdout.strip()


def cas_lease(backend, request, root, remote):
  """Atomically claim/transfer/release a destination via scoped force-with-lease.

  A failed or ambiguous push is resolved against the exact persisted commit,
  including the request ID; a stale writer must never be reported successful.
  """
  repository = backend.repository
  dest = request["parameters"]["destination"]
  ref = _ref(repository, dest)
  p = request["parameters"]
  expected = (p["expected_generation"], p["expected_holder"],
              p["expected_guid"])
  proposed = (p["holder"], p["guid"])
  root = Path(root)
  endpoint = _remote_scope(root, remote, backend)
  old_sha, previous = _read(backend, dest)
  old = (previous["generation"], previous["holder"], previous["guid"]) if (
    previous is not None) else (0, None, None)
  record = {"repository": repository, "destination": dest,
            "generation": p["expected_generation"] + 1,
            "holder": proposed[0], "guid": proposed[1],
            "request_id": request["request_id"]}
  _validate(record, repository, dest)
  if old != expected:
    if (previous == record and
        previous["request_id"] == request["request_id"]):
      return "unchanged", read_lease(backend, dest)
    raise LeaseProviderError("stale destination lease generation or owner")

  # CAS has no blanket override.  Only a force-with-lease of this one internal
  # tag is allowed, conditioned on exactly the provider-observed prior SHA.
  origin = ref if old_sha is not None else "refs/heads/" + dest
  fetching = _git(root, "fetch", "--no-tags", endpoint, origin)
  if fetching.returncode:
    raise LeaseProviderError("provider lease parent unavailable")
  parent = _git(root, "rev-parse", "--verify", "FETCH_HEAD")
  if parent.returncode or not _SHA.fullmatch(parent.stdout.strip()):
    raise LeaseProviderError("fetched lease parent invalid")
  if old_sha is not None and parent.stdout.strip() != old_sha:
    raise LeaseProviderError("provider lease ref changed during fetch")
  tree = _git(root, "rev-parse", "--verify", "FETCH_HEAD^{tree}")
  if tree.returncode or not _SHA.fullmatch(tree.stdout.strip()):
    raise LeaseProviderError("provider lease tree invalid")
  message = _PREFIX + json.dumps(record, sort_keys=True, separators=(",", ":"))
  commit = _git(root, "-c", "user.name=RepoWorkflow",
    "-c", "user.email=repoworkflow@users.noreply.github.com",
    "commit-tree", tree.stdout.strip(), "-p", parent.stdout.strip(),
    "-m", message)
  candidate = commit.stdout.strip()
  if commit.returncode or not _SHA.fullmatch(candidate):
    raise LeaseProviderError("cannot prepare immutable lease record")
  lease_expect = old_sha if old_sha is not None else ""
  push = _git(root, "push", "--porcelain",
    "--force-with-lease=" + ref + ":" + lease_expect,
    endpoint, "+" + candidate + ":" + ref)
  observed_sha, observed = _read(backend, dest)
  if observed_sha != candidate or observed != record:
    raise LeaseProviderError("lease CAS rejected or provider outcome UNKNOWN")
  if push.returncode:
    # Exact provider readback proves the committed operation despite a lost
    # response, but the caller must not claim an unverified fresh mutation.
    return "unchanged", read_lease(backend, dest)
  return "applied", read_lease(backend, dest)
