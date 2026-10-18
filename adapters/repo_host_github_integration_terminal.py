"""Immutable provider terminal ledger primitive for integration host v2 (#681).

An append-only tag records an attempt result.  It is not a READY queue item,
lease, or evidence that a merge occurred; the caller must supply independent
provider terminal evidence before any publication is authorized.
"""
import json
import re

from repo_workflow.integration_host_v2 import _valid_terminal


class TerminalProviderError(RuntimeError):
  """Durable authenticated terminal identity unavailable or inconsistent."""


_PREFIX = "RWF-INTEGRATION-TERMINAL-V2 "
_SHA = re.compile(r"[0-9a-f]{40}\Z")


def _ref(guid):
  if type(guid) is not str or re.fullmatch(
      r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", guid) is None:
    raise TerminalProviderError("invalid terminal GUID")
  return "refs/tags/rwf-integration-terminal-v2-" + guid


def _canonical(value):
  return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _read(backend, guid):
  """Read exact immutable Git commit and canonical result, not caller input."""
  ref = _ref(guid)
  try:
    response = backend.get("git/ref/tags/" + ref.split("/")[-1])
  except Exception as error:
    if getattr(error, "code", None) == "not_found":
      return None
    raise TerminalProviderError("terminal provider ref UNKNOWN") from error
  if (type(response) is not dict or response.get("ref") != ref
      or type(response.get("object")) is not dict):
    raise TerminalProviderError("terminal ref identity mismatch")
  sha = response["object"].get("sha")
  if type(sha) is not str or _SHA.fullmatch(sha) is None:
    raise TerminalProviderError("terminal commit SHA malformed")
  try:
    commit = backend.get("git/commits/" + sha)
  except Exception as error:
    raise TerminalProviderError("terminal commit unreadable") from error
  if type(commit) is not dict or type(commit.get("message")) is not str:
    raise TerminalProviderError("terminal commit malformed")
  message = commit["message"]
  if not message.startswith(_PREFIX):
    raise TerminalProviderError("terminal commit signature missing")
  try:
    record = json.loads(message[len(_PREFIX):])
  except ValueError as error:
    raise TerminalProviderError("terminal record is not JSON") from error
  if (not _valid_terminal(record, guid, backend.repository)
      or _canonical(record) != message[len(_PREFIX):]):
    raise TerminalProviderError("terminal identity or encoding mismatch")
  return record


def read_terminal(backend, guid):
  """Read provider-persisted record or None; never synthesize a terminal PASS."""
  return _read(backend, guid)


def record_terminal(backend, record, *, authorized, verify_evidence):
  """Create-once terminal evidence, with fail-closed outcome reconciliation.

  verify_evidence is a separate authenticated verifier for complete external
  testing, landing and authorization facts; this primitive never constructs
  those facts or accepts a bare unverified client result.
  """
  if (authorized is not True or type(record) is not dict
      or not _valid_terminal(record, record.get("guid"), backend.repository)):
    raise TerminalProviderError("terminal record is invalid or unauthorized")
  if record["status"] == "deferred-mit":
    # A deferred submission is resumable.  Freezing this GUID into an
    # immutable terminal tag would prevent later coordinated MIT recovery.
    raise TerminalProviderError("deferred MIT needs resumable event history")
  if not callable(verify_evidence) or verify_evidence(record) is not True:
    raise TerminalProviderError("independent terminal evidence unavailable")
  guid = record["guid"]
  existing = _read(backend, guid)
  if existing is not None:
    if existing != record:
      raise TerminalProviderError("terminal GUID already bound to another result")
    return "unchanged", {"guid": guid, "record": existing}
  # A terminal record lives on a commit under a tag namespace.  It never
  # advances main, PRELIM, INT-ATTEMPT or the destination.
  try:
    parent = backend.get("git/ref/heads/" +
                         record["destination_ref"].removeprefix("refs/heads/"))
    tip = parent["object"]["sha"]
    base_commit = backend.get("git/commits/" + tip)
    tree = base_commit["tree"]["sha"]
    if (type(tip) is not str or _SHA.fullmatch(tip) is None
        or type(tree) is not str or _SHA.fullmatch(tree) is None):
      raise TerminalProviderError("destination tree identity malformed")
  except TerminalProviderError:
    raise
  except Exception as error:
    raise TerminalProviderError("destination identity unavailable") from error
  if record["status"] == "integrated":
    # The provider, rather than a caller assertion, must confirm both the
    # accepted INT-ATTEMPT and landed commit remain in destination history.
    for base, head in (
        (record["accepted_sha"], record["landed_sha"]),
        (record["landed_sha"], tip)):
      try:
        proof = backend.get("compare/" + base + "..." + head)
      except Exception as error:
        raise TerminalProviderError("landed ancestry read UNKNOWN") from error
      if (type(proof) is not dict
          or type(proof.get("merge_base_commit")) is not dict
          or proof["merge_base_commit"].get("sha") != base):
        raise TerminalProviderError("landed ancestry not proved")
  try:
    made = backend.post("git/commits", {
      "message": _PREFIX + _canonical(record),
      "tree": tree, "parents": [tip],
    })
    commit_sha = made["sha"]
    if type(commit_sha) is not str or _SHA.fullmatch(commit_sha) is None:
      raise TerminalProviderError("terminal commit identity malformed")
    backend.post("git/refs", {"ref": _ref(guid), "sha": commit_sha})
  except Exception as error:
    # Lost mutation replies must be reconciled by independently reading back
    # the immutable request identity.  Matching just a candidate SHA is NOT
    # equivalent to checking a full terminal record.
    persisted = _read(backend, guid)
    if persisted == record:
      return "unchanged", {"guid": guid, "record": persisted}
    raise TerminalProviderError("terminal publication UNKNOWN") from error
  persisted = _read(backend, guid)
  if persisted != record:
    raise TerminalProviderError("terminal publication readback mismatch")
  return "applied", {"guid": guid, "record": persisted}


_RETIREMENT_FIELDS = (
  "status", "prelim_ref", "prelim_sha", "int_attempt_ref",
  "accepted_sha", "destination_ref", "landed_sha",
  "integration_id", "terminal_evidence_ref",
)


def retirement_terminal_reader(backend, landed):
  """Adapt provider v2 full ledger to #103's exact terminal callback shape.

  The returned callback accepts the terminal evidence reference expected by
  #103.  It re-reads the provider's immutable ledger by verified attempt GUID,
  preserving all #103 equality checks; it cannot synthesize provider evidence.
  """
  try:
    prelim = landed.prelim_ref
    attempt = landed.int_attempt_ref
    guid = prelim[-36:]
    if (not prelim.endswith("-" + guid)
        or not attempt.endswith("-" + guid)
        or not isinstance(landed.terminal_evidence_ref, str)
        or not landed.terminal_evidence_ref):
      raise TerminalProviderError("retirement attempt identity malformed")
    _ref(guid)
  except (AttributeError, TypeError, ValueError) as error:
    raise TerminalProviderError("retirement identity unavailable") from error

  def reader(evidence_ref):
    if evidence_ref != landed.terminal_evidence_ref:
      raise TerminalProviderError("terminal evidence request differs")
    record = read_terminal(backend, guid)
    if record is None or record["status"] != "integrated":
      raise TerminalProviderError("provider terminal integration absent")
    expected = {
      "prelim_ref": landed.prelim_ref,
      "prelim_sha": landed.prelim_sha,
      "int_attempt_ref": landed.int_attempt_ref,
      "accepted_sha": landed.accepted_sha,
      "destination_ref": landed.destination_ref,
      "landed_sha": landed.landed_sha,
      "integration_id": landed.integration_id,
      "terminal_evidence_ref": landed.terminal_evidence_ref,
    }
    if any(record.get(key) != value for key, value in expected.items()):
      raise TerminalProviderError("provider terminal landing differs")
    return {key: record[key] for key in _RETIREMENT_FIELDS}

  return reader
