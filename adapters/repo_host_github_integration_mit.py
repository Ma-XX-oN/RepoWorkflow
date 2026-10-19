"""Provider-persisted resumable MIT events, separate from terminal results.

Each lease generation has one create-once immutable event or authorization.
These Git tags are evidence history, not a second READY submission queue.
"""
import json
import re

from repo_workflow.integration_host_v2 import _valid_mit_record


class MitProviderError(RuntimeError):
  """MIT handoff authority or persistent provider history is unavailable."""


_SHA = re.compile(r"[0-9a-f]{40}\Z")
_GUID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z")
_KINDS = {"deferred": "event", "resume": "authorization"}
_MESSAGE = "RWF-MIT-EVIDENCE-V2 "
_MAX_PAGES = 100


def _ref(kind, guid, generation):
  if (kind not in _KINDS or type(guid) is not str
      or _GUID.fullmatch(guid) is None
      or type(generation) is not int or not 1 <= generation < 10**12):
    raise MitProviderError("invalid MIT record identity")
  return ("refs/tags/rwf-mit-" + kind + "-v2-" + guid +
          "-" + str(generation).zfill(12))


def _canonical(value):
  return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _validate(backend, record, kind, guid, destination):
  if not _valid_mit_record(record, guid, destination, backend.repository,
                           resume=(kind == "resume")):
    raise MitProviderError("MIT persisted record identity invalid")
  generation = record[
    "expected_generation" if kind == "resume" else "lease_generation"]
  _ref(kind, guid, generation)
  return generation


def _read_at(backend, kind, guid, destination, generation):
  ref = _ref(kind, guid, generation)
  try:
    reply = backend.get("git/ref/tags/" + ref.rsplit("/", 1)[1])
  except Exception as error:
    if getattr(error, "code", None) == "not_found":
      return None
    raise MitProviderError("MIT provider record read UNKNOWN") from error
  if (type(reply) is not dict or reply.get("ref") != ref
      or type(reply.get("object")) is not dict):
    raise MitProviderError("MIT provider ref differs")
  sha = reply["object"].get("sha")
  if type(sha) is not str or _SHA.fullmatch(sha) is None:
    raise MitProviderError("MIT record commit SHA invalid")
  try:
    message = backend.get("git/commits/" + sha)["message"]
    if type(message) is not str or not message.startswith(_MESSAGE):
      raise ValueError("invalid MIT message")
    record = json.loads(message[len(_MESSAGE):])
  except (KeyError, ValueError, TypeError) as error:
    raise MitProviderError("MIT evidence commit malformed") from error
  if _canonical(record) != message[len(_MESSAGE):]:
    raise MitProviderError("MIT record encoding differs")
  if _validate(backend, record, kind, guid, destination) != generation:
    raise MitProviderError("MIT record generation differs")
  return record


def read_mit(backend, kind, guid, destination):
  """Read newest durable event; fail closed on incomplete inventory."""
  if kind not in _KINDS or type(guid) is not str or _GUID.fullmatch(guid) is None:
    raise MitProviderError("invalid MIT lookup")
  prefix = "refs/tags/rwf-mit-" + kind + "-v2-" + guid + "-"
  generations = set()
  for page in range(1, _MAX_PAGES + 1):
    route = ("git/matching-refs/tags/" + prefix.removeprefix("refs/tags/")
             + "?per_page=100&page=" + str(page))
    try:
      payload = backend.get(route)
    except Exception as error:
      raise MitProviderError("MIT event inventory UNKNOWN") from error
    if type(payload) is not list or len(payload) > 100:
      raise MitProviderError("MIT event inventory malformed")
    for value in payload:
      if (type(value) is not dict or type(value.get("ref")) is not str
          or not value["ref"].startswith(prefix)):
        raise MitProviderError("MIT event inventory ref invalid")
      suffix = value["ref"][len(prefix):]
      if (len(suffix) != 12 or not suffix.isascii()
          or not suffix.isdecimal()):
        raise MitProviderError("MIT event generation invalid")
      generation = int(suffix)
      if generation < 1 or generation in generations:
        raise MitProviderError("MIT duplicate generation")
      generations.add(generation)
    if len(payload) < 100:
      if not generations:
        return None
      return _read_at(backend, kind, guid, destination, max(generations))
  raise MitProviderError("MIT event inventory truncated")


def record_mit(backend, kind, record, *, verify_evidence):
  """Create immutable provider event after independent authorization proof."""
  if kind not in _KINDS or type(record) is not dict:
    raise MitProviderError("invalid MIT record")
  guid = record.get("guid")
  dest = record.get("destination")
  generation = _validate(backend, record, kind, guid, dest)
  if not callable(verify_evidence) or verify_evidence(record) is not True:
    raise MitProviderError("independent MIT evidence/authority unavailable")
  # Neither deferral nor resumption may bypass an already terminal attempt.
  from adapters.repo_host_github_integration_terminal import read_terminal
  if read_terminal(backend, guid) is not None:
    raise MitProviderError("terminal attempt forbids MIT reuse")
  existing = _read_at(backend, kind, guid, dest, generation)
  if existing is not None:
    if existing != record:
      raise MitProviderError("MIT generation already has different evidence")
    return "unchanged", existing
  try:
    head = backend.get("git/ref/heads/" + dest)
    if head.get("ref") != "refs/heads/" + dest:
      raise ValueError("MIT parent ref differs")
    sha = head["object"]["sha"]
    tree = backend.get("git/commits/" + sha)["tree"]["sha"]
    if any(type(v) is not str or _SHA.fullmatch(v) is None
           for v in (sha, tree)):
      raise ValueError("MIT parent identity malformed")
    made = backend.post("git/commits", {
      "message": _MESSAGE + _canonical(record),
      "tree": tree, "parents": [sha]})
    commit = made["sha"]
    if type(commit) is not str or _SHA.fullmatch(commit) is None:
      raise ValueError("MIT evidence commit malformed")
    backend.post("git/refs", {
      "ref": _ref(kind, guid, generation), "sha": commit})
  except Exception as error:
    if _read_at(backend, kind, guid, dest, generation) == record:
      return "unchanged", record
    raise MitProviderError("MIT event publication UNKNOWN") from error
  persisted = _read_at(backend, kind, guid, dest, generation)
  if persisted != record:
    raise MitProviderError("MIT event readback mismatch")
  return "applied", persisted
