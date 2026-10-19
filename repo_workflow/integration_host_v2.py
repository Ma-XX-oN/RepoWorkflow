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
  r"refs/heads/INT-ATTEMPT-[A-Za-z0-9._-]+/"
  r"[A-Za-z0-9._/-]+-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z")
_OPERATIONS = {
  "destination.read": {"destination"},
  "refs.list": {"prefix"},
  "ref.create": {"ref", "sha"},
  "ref.cas": {"ref", "expected_sha", "sha"},
  "lease.read": {"destination"},
  "lease.cas": {"destination", "expected_generation",
                "expected_holder", "expected_guid", "holder", "guid"},
  "attempt.read": {"guid"},
  "attempt.record": {"guid", "record"},
  "mit.deferred.read": {"guid", "destination"},
  "mit.deferred.record": {"guid", "destination", "event"},
  "mit.resume.read": {"guid", "destination"},
  "mit.resume.record": {"guid", "destination", "authorization"},
  "retirement.read": {"guid", "ref_kind"},
  "retirement.record": {"guid", "ref_kind", "record"},
}
_STATUSES = {"integrated", "failed", "rejected"}
_TERMINAL_FIELDS = {
  "repository", "guid", "status", "prelim_ref", "prelim_sha",
  "int_attempt_ref", "accepted_sha", "destination_ref",
  "expected_destination_sha", "observed_destination_sha",
  "landed_sha", "integration_id", "provider_operation_id", "umbrella",
  "terminal_evidence_ref",
}


def _valid_terminal(value, guid, repository=None):
  """A terminal result must contain independent exact integration identities."""
  if type(value) is not dict or set(value) != _TERMINAL_FIELDS:
    return False
  if value["guid"] != guid or value["status"] not in _STATUSES:
    return False
  if (type(value["repository"]) is not str
      or re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+",
                      value["repository"]) is None):
    return False
  if repository is not None and value["repository"] != repository:
    return False
  for name in ("prelim_sha", "accepted_sha", "expected_destination_sha",
               "observed_destination_sha"):
    if type(value[name]) is not str or _SHA.fullmatch(value[name]) is None:
      return False
  landed = value["landed_sha"]
  if value["status"] == "integrated":
    if type(landed) is not str or _SHA.fullmatch(landed) is None:
      return False
  elif landed is not None:
    return False
  if (type(value["destination_ref"]) is not str
      or not value["destination_ref"].startswith("refs/heads/")):
    return False
  scopes = []
  for key, prefix in (("prelim_ref", "PRELIM-"),
                      ("int_attempt_ref", "INT-ATTEMPT-")):
    ref = value[key]
    marker = "refs/heads/" + prefix
    if type(ref) is not str or not ref.startswith(marker):
      return False
    if not ref.endswith("-" + guid):
      return False
    scope = ref[len(marker):-(len(guid) + 1)]
    if "/" not in scope:
      return False
    umbrella, destination = scope.split("/", 1)
    if (not umbrella or not destination
        or any(x in ("", ".", "..") for x in destination.split("/"))):
      return False
    scopes.append((umbrella, destination))
  if (scopes[0] != scopes[1] or
      value["destination_ref"] != "refs/heads/" + scopes[0][1]
      or value["umbrella"] != scopes[0][0]):
    return False
  if (type(value["integration_id"]) is not str
      or _ID.fullmatch(value["integration_id"]) is None
      or type(value["provider_operation_id"]) is not str
      or _ID.fullmatch(value["provider_operation_id"]) is None
      or type(value["terminal_evidence_ref"]) is not str
      or not value["terminal_evidence_ref"].strip()):
    return False
  return True


_MIT_DEFER_FIELDS = {
  "repository", "guid", "destination", "prelim_sha",
  "lease_generation", "evidence_ref", "reason",
}
_MIT_RESUME_FIELDS = {
  "repository", "guid", "destination", "prelim_sha",
  "expected_generation", "deferred_evidence_ref", "evidence_ref",
  "approved",
}


def _valid_mit_record(value, guid, destination, repository, *, resume):
  fields = _MIT_RESUME_FIELDS if resume else _MIT_DEFER_FIELDS
  if type(value) is not dict or set(value) != fields:
    return False
  if (value["guid"] != guid or value["destination"] != destination
      or value["repository"] != repository
      or type(value["prelim_sha"]) is not str
      or _SHA.fullmatch(value["prelim_sha"]) is None):
    return False
  key = "expected_generation" if resume else "lease_generation"
  if type(value[key]) is not int or value[key] < 1:
    return False
  refs = ("evidence_ref", "deferred_evidence_ref") if resume else ("evidence_ref",)
  if any(type(value[k]) is not str or not value[k].strip() for k in refs):
    return False
  if resume:
    return type(value["approved"]) is bool
  return value["reason"] in {"timeout", "awaiting-manual"}


_RETIREMENT_FIELDS = {
  "repository", "guid", "ref_kind", "retired_ref", "expected_sha",
  "operation_id", "terminal_evidence_ref", "destination_ref",
  "landed_sha", "outcome",
}


def _valid_retirement(record, guid, kind, repository):
  if (type(record) is not dict or set(record) != _RETIREMENT_FIELDS
      or record["repository"] != repository or record["guid"] != guid
      or record["ref_kind"] != kind or
      record["outcome"] != "retired"):
    return False
  if kind not in {"PRELIM", "INT-ATTEMPT"}:
    return False
  if any(type(record[k]) is not str or _SHA.fullmatch(record[k]) is None
         for k in ("expected_sha", "landed_sha")):
    return False
  marker = "refs/heads/" + kind + "-"
  if (type(record["retired_ref"]) is not str
      or not record["retired_ref"].startswith(marker)
      or not record["retired_ref"].endswith("-" + guid)
      or type(record["destination_ref"]) is not str
      or not record["destination_ref"].startswith("refs/heads/")
      or type(record["operation_id"]) is not str
      or _ID.fullmatch(record["operation_id"]) is None
      or type(record["terminal_evidence_ref"]) is not str
      or not record["terminal_evidence_ref"].strip()):
    return False
  return True


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
  if op == "attempt.record":
    return _valid_terminal(values["record"], values["guid"])
  if op.startswith("mit."):
    if op.endswith(".read"):
      return True
    kind = "authorization" if op.startswith("mit.resume") else "event"
    # Repository identity is authenticated against IntegrationHost.repository.
    return _valid_mit_record(
      values[kind], values["guid"], values["destination"],
      values[kind].get("repository") if type(values[kind]) is dict else None,
      resume=(kind == "authorization"))
  if op.startswith("retirement."):
    if values["ref_kind"] not in ("PRELIM", "INT-ATTEMPT"):
      return False
    if op == "retirement.record":
      record = values["record"]
      return (type(record) is dict and
              _valid_retirement(record, values["guid"],
                                values["ref_kind"], record.get("repository")))
  return True


def _valid_result(operation, request, result):
  if type(result) is not dict:
    return False
  if operation == "destination.read":
    return (
      set(result) == {"destination", "ref", "sha",
                      "policy_present", "policy_text"}
      and result["destination"] == request["destination"]
      and result["ref"] == "refs/heads/" + request["destination"]
      and type(result["sha"]) is str
      and _SHA.fullmatch(result["sha"]) is not None
      and type(result["policy_present"]) is bool
      and ((result["policy_present"] and
            type(result["policy_text"]) is str)
           or (not result["policy_present"] and
               result["policy_text"] is None))
    )
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
    structurally_valid = (
      result["destination"] == request["destination"]
      and type(result["generation"]) is int and result["generation"] >= 0
      and (result["holder"] is None) == (result["guid"] is None)
      and (result["holder"] is None or (
        type(result["holder"]) is str and bool(result["holder"])))
      and (result["guid"] is None or (
        type(result["guid"]) is str and
        _GUID.fullmatch(result["guid"]) is not None)))
    if not structurally_valid:
      return False
    if operation == "lease.cas":
      return (result["generation"] == request["expected_generation"] + 1
        and result["holder"] == request["holder"]
        and result["guid"] == request["guid"])
    return True
  if operation in {"attempt.read", "attempt.record"}:
    if set(result) != {"guid", "record"} or (
        result["guid"] != request["guid"]):
      return False
    if result["record"] is None:
      return operation == "attempt.read"
    if not _valid_terminal(result["record"], request["guid"]):
      return False
    return (operation == "attempt.read" or
            result["record"] == request["record"])
  if operation.startswith("mit."):
    key = "authorization" if operation.startswith("mit.resume") else "event"
    if (set(result) != {"guid", "destination", key}
        or result["guid"] != request["guid"]
        or result["destination"] != request["destination"]):
      return False
    record = result[key]
    if record is None:
      return operation.endswith(".read")
    if not _valid_mit_record(
        record, request["guid"], request["destination"],
        record.get("repository") if type(record) is dict else None,
        resume=(key == "authorization")):
      return False
    return operation.endswith(".read") or record == request[key]
  if operation in {"retirement.read", "retirement.record"}:
    if (set(result) != {"guid", "ref_kind", "record"}
        or result["guid"] != request["guid"]
        or result["ref_kind"] != request["ref_kind"]):
      return False
    if result["record"] is None:
      return operation == "retirement.read"
    if not _valid_retirement(result["record"], request["guid"],
                             request["ref_kind"],
                             result["record"].get("repository")
                             if type(result["record"]) is dict else None):
      return False
    return (operation == "retirement.read" or
            result["record"] == request["record"])
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
    if (operation == "attempt.record" and
        not _valid_terminal(parameters["record"],
                            parameters["guid"], self.repository)):
      raise IntegrationHostError("terminal record repository mismatch")
    if operation.startswith("mit.") and operation.endswith(".record"):
      key = "authorization" if operation.startswith("mit.resume") else "event"
      if not _valid_mit_record(
          parameters[key], parameters["guid"], parameters["destination"],
          self.repository, resume=(key == "authorization")):
        raise IntegrationHostError("MIT event repository or identity mismatch")
    if operation == "retirement.record" and (
        parameters["record"]["repository"] != self.repository or
        parameters["record"]["operation_id"] != request_id):
      raise IntegrationHostError("retirement request/repository binding mismatch")
    request = dict(schema_version=2, repository=self.repository,
                   operation=operation, request_id=request_id,
                   parameters=parameters)
    try:
      reply = self.transport(request)
    except IntegrationHostError:
      raise
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
    if (operation in {"destination.read", "refs.list", "lease.read",
                      "attempt.read", "retirement.read",
                      "mit.deferred.read", "mit.resume.read"}
        and reply["status"] != "unchanged"):
      raise IntegrationHostError("read-only provider operation claimed mutation")
    if not _valid_result(operation, parameters, reply["result"]):
      raise IntegrationHostError("invalid integration provider result")
    if operation.startswith("mit."):
      key = "authorization" if operation.startswith("mit.resume") else "event"
      event = reply["result"][key]
      if event is not None and not _valid_mit_record(
          event, parameters["guid"], parameters["destination"],
          self.repository, resume=(key == "authorization")):
        raise IntegrationHostError("provider MIT record repository mismatch")
    if (operation in {"attempt.read", "attempt.record"}
        and reply["result"]["record"] is not None
        and not _valid_terminal(reply["result"]["record"],
                                parameters["guid"], self.repository)):
      raise IntegrationHostError("provider terminal repository mismatch")
    if operation in {"retirement.read", "retirement.record"} and (
        reply["result"]["record"] is not None and
        not _valid_retirement(reply["result"]["record"], parameters["guid"],
                               parameters["ref_kind"], self.repository)):
      raise IntegrationHostError("provider retirement repository mismatch")
    return reply["result"]
