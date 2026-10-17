"""Versioned provider-neutral integration-host request/response boundary.

Strict transport validation, not provider-side enforcement. Repo-host v1 stays
unchanged; callers must reject absent v2 capability.
"""
from collections.abc import Callable
import re


class IntegrationHostError(RuntimeError):
  """Provider protocol, capability, or persisted response is untrusted."""


_SHA = re.compile(r"[0-9a-f]{40}\Z")
_GUID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z")
_ID = re.compile(r"[A-Za-z0-9._:-]{1,128}\Z")
_REF = re.compile(
  r"refs/heads/INT-ATTEMPT-issue-[1-9][0-9]*/"
  r"[A-Za-z0-9._/-]+-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z")
_OPERATIONS = {
  "refs.list": {"prefix"},
  "ref.create": {"ref", "sha"},
  "ref.cas": {"ref", "expected_sha", "sha"},
  "lease.read": {"destination"},
  "lease.cas": {"destination", "expected_generation",
                "expected_holder", "expected_guid", "holder", "guid"},
  "attempt.read": {"guid"},
  "attempt.record": {"guid", "status", "sha"},
}
_STATUSES = {"integrated", "failed", "rejected", "deferred-mit"}


def _valid_ref(ref):
  if type(ref) is not str or not _REF.fullmatch(ref):
    return False
  suffix = ref.split("/", 3)[3]
  destination = suffix[:-37]
  return all(part and part not in (".", "..")
             for part in destination.split("/"))


def _valid_params(op, values):
  if type(values) is not dict or set(values) != _OPERATIONS[op]:
    return False
  for key, value in values.items():
    if key.endswith("sha") and (
        type(value) is not str or not _SHA.fullmatch(value)):
      return False
    if key == "expected_generation" and (
        type(value) is not int or value < 0):
      return False
    if key in {"guid", "expected_guid"} and value is not None and (
        type(value) is not str or not _GUID.fullmatch(value)):
      return False
    if key in {"holder", "expected_holder"} and value is not None and (
        type(value) is not str or not value.strip()):
      return False
    if key == "status" and value not in _STATUSES:
      return False
    if key == "destination" and (
        type(value) is not str or not value or
        any(part in ("", ".", "..") for part in value.split("/"))):
      return False
  if op == "refs.list":
    return values["prefix"] == "refs/heads/PRELIM-"
  if op in {"ref.create", "ref.cas"}:
    return _valid_ref(values["ref"])
  if op == "lease.cas":
    return ((values["expected_guid"] is None) ==
            (values["expected_holder"] is None) and
            (values["guid"] is None) == (values["holder"] is None))
  return True


def _valid_result(operation, request, result):
  if type(result) is not dict:
    return False
  if operation == "refs.list":
    return (set(result) == {"refs"} and type(result["refs"]) is dict
      and all(type(ref) is str and ref.startswith("refs/heads/PRELIM-")
              and type(sha) is str and _SHA.fullmatch(sha)
              for ref, sha in result["refs"].items()))
  if operation in {"ref.create", "ref.cas"}:
    return (set(result) == {"ref", "sha"} and
            result["ref"] == request["ref"] and
            result["sha"] == request["sha"])
  if operation in {"lease.read", "lease.cas"}:
    if set(result) != {"destination", "generation", "holder", "guid"}:
      return False
    return (result["destination"] == request["destination"]
      and type(result["generation"]) is int and result["generation"] >= 0
      and (result["holder"] is None) == (result["guid"] is None)
      and (result["holder"] is None or (
        type(result["holder"]) is str and bool(result["holder"])))
      and (result["guid"] is None or (
        type(result["guid"]) is str and
        _GUID.fullmatch(result["guid"]) is not None)))
  if operation in {"attempt.read", "attempt.record"}:
    if set(result) != {"guid", "status", "sha"} or (
        result["guid"] != request["guid"]):
      return False
    if result["status"] is None:
      return operation == "attempt.read" and result["sha"] is None
    return (result["status"] in _STATUSES
      and type(result["sha"]) is str and
      _SHA.fullmatch(result["sha"]) is not None
      and (operation == "attempt.read" or (
        result["status"] == request["status"] and
        result["sha"] == request["sha"])))
  return False


class IntegrationHost:
  def __init__(self, repository: str, transport: Callable[[dict], dict]):
    if (type(repository) is not str or
        re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) is None):
      raise IntegrationHostError("invalid repository identity")
    self.repository = repository
    self.transport = transport

  def request(self, operation: str, request_id: str, parameters: dict) -> dict:
    if operation not in _OPERATIONS:
      raise IntegrationHostError("unsupported integration operation")
    if type(request_id) is not str or _ID.fullmatch(request_id) is None:
      raise IntegrationHostError("invalid idempotency key")
    if not _valid_params(operation, parameters):
      raise IntegrationHostError("invalid integration parameters")
    request = dict(schema_version=2, repository=self.repository,
                   operation=operation, request_id=request_id,
                   parameters=parameters)
    try:
      reply = self.transport(request)
    except Exception as error:
      raise IntegrationHostError("provider outcome UNKNOWN; reconcile") from error
    if (type(reply) is not dict or set(reply) != {
        "schema_version", "repository", "operation", "request_id",
        "status", "result"}):
      raise IntegrationHostError("malformed integration provider response")
    if (type(reply["schema_version"]) is not int or
        reply["schema_version"] != 2 or
        reply["repository"] != self.repository or
        reply["operation"] != operation or
        reply["request_id"] != request_id or
        reply["status"] not in {"applied", "unchanged"} or
        type(reply["status"]) is not str):
      raise IntegrationHostError("integration provider response identity mismatch")
    if not _valid_result(operation, parameters, reply["result"]):
      raise IntegrationHostError("invalid integration provider result")
    return reply["result"]
