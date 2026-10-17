"""Versioned provider-neutral integration-host request boundary.

This is a strict transport contract, not an implied server implementation.
Repo-host v1's existing six mutation operations remain unchanged.
"""
from collections.abc import Callable
import re


class IntegrationHostError(RuntimeError):
  """Provider protocol, capability, or persisted response is untrusted."""


_SHA = re.compile(r"[0-9a-f]{40}\Z")
_REQUEST_ID = re.compile(r"[A-Za-z0-9._:-]{1,128}\Z")
_OPERATIONS = {
  "refs.list": frozenset({"prefix"}),
  "ref.create": frozenset({"ref", "sha"}),
  "ref.cas": frozenset({"ref", "expected_sha", "sha"}),
  "lease.read": frozenset({"destination"}),
  "lease.cas": frozenset({"destination", "expected_generation",
                          "expected_holder", "expected_guid",
                          "holder", "guid"}),
  "attempt.read": frozenset({"guid"}),
  "attempt.record": frozenset({"guid", "status", "sha"}),
}


def _full_sha(value):
  return type(value) is str and _SHA.fullmatch(value) is not None


def _valid_params(op, parameters):
  if type(parameters) is not dict or set(parameters) != _OPERATIONS[op]:
    return False
  for key, value in parameters.items():
    if key.endswith("sha") and not _full_sha(value):
      return False
    if key == "expected_generation" and (type(value) is not int or value < 0):
      return False
    if key in {"guid", "holder", "expected_guid", "expected_holder"}:
      if value is not None and (type(value) is not str or not value):
        return False
    if key == "status" and value not in {
        "integrated", "failed", "rejected", "deferred-mit"}:
      return False
    if key in {"prefix", "ref", "destination"} and (
        type(value) is not str or not value):
      return False
  if op == "refs.list" and parameters["prefix"] != "refs/heads/PRELIM-":
    return False
  if op in {"ref.create", "ref.cas"} and not parameters["ref"].startswith(
      "refs/heads/INT-ATTEMPT-"):
    return False
  return True


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
    if type(request_id) is not str or _REQUEST_ID.fullmatch(request_id) is None:
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
    if (type(reply["schema_version"]) is not int
        or reply["schema_version"] != 2
        or reply["repository"] != self.repository
        or reply["operation"] != operation
        or reply["request_id"] != request_id
        or reply["status"] not in {"applied", "unchanged"}
        or type(reply["result"]) is not dict):
      raise IntegrationHostError("integration provider response identity mismatch")
    return reply["result"]
