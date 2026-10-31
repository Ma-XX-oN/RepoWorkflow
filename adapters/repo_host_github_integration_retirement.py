"""Immutable provider-retirement audit: evidence after conditional ref deletion.

#103 owns exact-old-SHA conditional deletion and independent landing checks.
This component does not delete any ref; it persists an authenticated proof of
an observed deletion after the caller's trusted verifier independently passes.
"""
import json
import re

from adapters.repo_host_github_integration_terminal import read_terminal


class RetirementAuditError(RuntimeError):
  """Deletion evidence is absent, conflicting or unauthenticated."""


_SHA = re.compile(r"[0-9a-f]{40}\Z")
_GUID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z")
_ID = re.compile(r"[A-Za-z0-9._:-]{1,128}\Z")
_PREFIX = "RWF-INTEGRATION-RETIREMENT-V2 "
_FIELDS = {
  "repository", "guid", "ref_kind", "retired_ref", "expected_sha",
  "operation_id", "terminal_evidence_ref", "destination_ref",
  "landed_sha", "outcome",
}


def _ref(guid, kind):
  if (type(guid) is not str or _GUID.fullmatch(guid) is None
      or kind not in ("PRELIM", "INT-ATTEMPT")):
    raise RetirementAuditError("invalid retirement audit identity")
  return ("refs/tags/rwf-integration-ref-retired-v2-" +
          guid + "-" + kind.lower())


def _canonical(value):
  return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _validate(backend, record):
  if type(record) is not dict or set(record) != _FIELDS:
    raise RetirementAuditError("retirement audit schema invalid")
  guid = record["guid"]
  kind = record["ref_kind"]
  _ref(guid, kind)
  if record["repository"] != backend.repository:
    raise RetirementAuditError("retirement audit repository mismatch")
  if (record["outcome"] != "retired" or
      type(record["expected_sha"]) is not str or
      _SHA.fullmatch(record["expected_sha"]) is None or
      type(record["landed_sha"]) is not str or
      _SHA.fullmatch(record["landed_sha"]) is None or
      type(record["operation_id"]) is not str or
      _ID.fullmatch(record["operation_id"]) is None):
    raise RetirementAuditError("retirement audit result malformed")
  if (type(record["terminal_evidence_ref"]) is not str
      or not record["terminal_evidence_ref"].strip()
      or type(record["destination_ref"]) is not str
      or not record["destination_ref"].startswith("refs/heads/")):
    raise RetirementAuditError("retirement evidence or destination invalid")
  terminal = read_terminal(backend, guid)
  if terminal is None or terminal["status"] != "integrated":
    raise RetirementAuditError("independent terminal landing absent")
  retired_ref = terminal[
    "prelim_ref" if kind == "PRELIM" else "int_attempt_ref"]
  accepted = terminal[
    "prelim_sha" if kind == "PRELIM" else "accepted_sha"]
  for key, value in (
      ("retired_ref", retired_ref), ("expected_sha", accepted),
      ("terminal_evidence_ref", terminal["terminal_evidence_ref"]),
      ("destination_ref", terminal["destination_ref"]),
      ("landed_sha", terminal["landed_sha"])):
    if record[key] != value:
      raise RetirementAuditError("retirement identity differs from terminal")
  return retired_ref


def _read(backend, guid, kind):
  ref = _ref(guid, kind)
  try:
    fetched = backend.get("git/ref/tags/" + ref.rsplit("/", 1)[1])
  except Exception as error:
    if getattr(error, "code", None) == "not_found":
      return None
    raise RetirementAuditError("retirement audit read UNKNOWN") from error
  if (type(fetched) is not dict or fetched.get("ref") != ref
      or type(fetched.get("object")) is not dict):
    raise RetirementAuditError("retirement tag ref malformed")
  sha = fetched["object"].get("sha")
  if type(sha) is not str or _SHA.fullmatch(sha) is None:
    raise RetirementAuditError("retirement tag SHA malformed")
  try:
    value = backend.get("git/commits/" + sha)
    message = value["message"]
    if type(message) is not str or not message.startswith(_PREFIX):
      raise ValueError("wrong retirement message")
    record = json.loads(message[len(_PREFIX):])
    if _canonical(record) != message[len(_PREFIX):]:
      raise ValueError("noncanonical retirement record")
    if record.get("guid") != guid or record.get("ref_kind") != kind:
      raise ValueError("retirement tag identity mismatch")
    _validate(backend, record)
  except Exception as error:
    raise RetirementAuditError("retirement audit identity invalid") from error
  return record


def read_retirement(backend, guid, kind):
  """Return a provider-backed immutable audit or None, never inferred success."""
  return _read(backend, guid, kind)


def _absent(backend, ref):
  try:
    backend.get("git/ref/" + ref.removeprefix("refs/"))
  except Exception as error:
    if getattr(error, "code", None) == "not_found":
      return True
    raise RetirementAuditError("deleted ref readback UNKNOWN") from error
  return False


def record_retirement(backend, record, *, verify_deletion):
  """Write create-once audit after independent post-delete verification.

  The verifier must authenticate the #103 conditional push, expected old SHA,
  request identity and provider readback. Absence alone is not authorization.
  """
  ref = _validate(backend, record)
  if (not callable(verify_deletion) or verify_deletion(record) is not True):
    raise RetirementAuditError("trusted deletion evidence unavailable")
  if not _absent(backend, ref):
    raise RetirementAuditError("retired provider ref still exists")
  old = _read(backend, record["guid"], record["ref_kind"])
  if old is not None:
    if old != record:
      raise RetirementAuditError("conflicting immutable retirement record")
    return "unchanged", old

  # Create a disconnected audit commit; the destination ref is never updated.
  try:
    dest = backend.get("git/ref/" +
                       record["destination_ref"].removeprefix("refs/"))
    if dest.get("ref") != record["destination_ref"]:
      raise ValueError("destination ref mismatch")
    tip = dest["object"]["sha"]
    commit = backend.get("git/commits/" + tip)
    tree = commit["tree"]["sha"]
    if not all(type(s) is str and _SHA.fullmatch(s) is not None
               for s in (tip, tree)):
      raise ValueError("bad destination commit")
    made = backend.post("git/commits", {
      "message": _PREFIX + _canonical(record),
      "tree": tree, "parents": [tip],
    })
    sha = made["sha"]
    if type(sha) is not str or _SHA.fullmatch(sha) is None:
      raise ValueError("bad audit commit")
    backend.post("git/refs", {
      "ref": _ref(record["guid"], record["ref_kind"]), "sha": sha})
  except Exception as error:
    persisted = _read(backend, record["guid"], record["ref_kind"])
    if persisted == record:
      return "unchanged", persisted
    raise RetirementAuditError("retirement audit publication UNKNOWN") from error
  persisted = _read(backend, record["guid"], record["ref_kind"])
  if persisted != record:
    raise RetirementAuditError("retirement audit readback differs")
  return "applied", persisted
