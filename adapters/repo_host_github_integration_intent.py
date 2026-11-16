"""Durable immutable operation identity for destination acceptance (#681).

An intent is audit/coordination evidence, never a READY queue or a claim that
integration landed. A fresh provider readback must confirm the destination.
"""
import hashlib
import json
import re


class AcceptanceIntentError(RuntimeError):
  """An operation's independently persisted identity is unverified."""


_SHA = re.compile(r"[0-9a-f]{40}\Z")
_PREFIX = "RWF-INTEGRATION-ACCEPTANCE-INTENT-V2 "


def _canonical(value):
  return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _reference(repository, operation_id):
  if (type(repository) is not str or
      re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) is None
      or type(operation_id) is not str
      or re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", operation_id) is None):
    raise AcceptanceIntentError("invalid integration operation identity")
  digest = hashlib.sha256(
    (repository + "\0" + operation_id).encode()).hexdigest()
  return "refs/tags/rwf-integration-acceptance-v2-" + digest


def _expected(request, actor):
  record = request["parameters"]["record"]
  return {
    "repository": request["repository"],
    "operation_id": request["request_id"],
    "actor_id": actor,
    "destination": record["destination"],
    "guid": record["guid"],
    "expected_destination_sha": record["expected_destination_sha"],
    "proposed_sha": record["proposed_sha"],
    "accepted_sha": record["accepted_sha"],
    "request_digest": hashlib.sha256(_canonical(request).encode()).hexdigest(),
  }


def _read(backend, request, actor):
  """Validate tag, exact canonical immutable commit and authenticated actor."""
  ref = _reference(request["repository"], request["request_id"])
  expected = _expected(request, actor)
  try:
    obj = backend.get("git/ref/tags/" + ref.rsplit("/", 1)[1])
  except Exception as error:
    if getattr(error, "code", None) == "not_found":
      return None
    raise AcceptanceIntentError("intent provider read UNKNOWN") from error
  if (type(obj) is not dict or obj.get("ref") != ref
      or type(obj.get("object")) is not dict):
    raise AcceptanceIntentError("intent ref is malformed")
  sha = obj["object"].get("sha")
  if type(sha) is not str or _SHA.fullmatch(sha) is None:
    raise AcceptanceIntentError("intent SHA is malformed")
  try:
    commit = backend.get("git/commits/" + sha)
    message = commit["message"]
    parents = commit["parents"]
    if (type(message) is not str or not message.startswith(_PREFIX)
        or type(parents) is not list or len(parents) != 1
        or type(parents[0]) is not dict
        or parents[0].get("sha") != expected["expected_destination_sha"]):
      raise ValueError("noncanonical acceptance intent parent")
    data = json.loads(message[len(_PREFIX):])
    if data != expected or _canonical(data) != message[len(_PREFIX):]:
      raise ValueError("conflicting acceptance intent")
  except Exception as error:
    raise AcceptanceIntentError("intent evidence identity invalid") from error
  return data


def read_intent(backend, request):
  """Return an independently persisted exact-request intent or None."""
  if request["repository"] != backend.repository:
    raise AcceptanceIntentError("foreign integration repository")
  try:
    actor = backend.identity()["login"]
  except Exception as error:
    raise AcceptanceIntentError("provider identity UNKNOWN") from error
  if type(actor) is not str or not actor:
    raise AcceptanceIntentError("provider actor invalid")
  return _read(backend, request, actor)


def publish_intent(backend, request):
  """Create-once ref with strict lost-response reconciliation.

  The parent of the intent audit commit is the expected destination SHA, so
  a changed request ID, destination, SHA, or actor cannot borrow the tag.
  """
  if request["repository"] != backend.repository:
    raise AcceptanceIntentError("foreign integration repository")
  try:
    actor = backend.identity()["login"]
  except Exception as error:
    raise AcceptanceIntentError("provider identity UNKNOWN") from error
  if type(actor) is not str or not actor:
    raise AcceptanceIntentError("provider actor invalid")
  expected = _expected(request, actor)
  existing = _read(backend, request, actor)
  if existing is not None:
    return existing
  old_sha = expected["expected_destination_sha"]
  try:
    base = backend.get("git/commits/" + old_sha)
    tree = base["tree"]["sha"]
    if type(tree) is not str or _SHA.fullmatch(tree) is None:
      raise ValueError("destination tree invalid")
    new_commit = backend.post("git/commits", {
      "message": _PREFIX + _canonical(expected),
      "tree": tree, "parents": [old_sha],
    })
    created_sha = new_commit["sha"]
    if type(created_sha) is not str or _SHA.fullmatch(created_sha) is None:
      raise ValueError("new intent commit invalid")
    backend.post("git/refs", {
      "ref": _reference(request["repository"], request["request_id"]),
      "sha": created_sha,
    })
  except Exception as error:
    reconciled = _read(backend, request, actor)
    if reconciled == expected:
      return reconciled
    raise AcceptanceIntentError("acceptance intent publication UNKNOWN") from error
  observed = _read(backend, request, actor)
  if observed != expected:
    raise AcceptanceIntentError("acceptance intent readback differs")
  return observed
