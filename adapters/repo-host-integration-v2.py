#!/usr/bin/env python3
"""Separate fail-closed GitHub integration-host v2 adapter (#681).

The existing repo-host v1 contract and executable remain unchanged.
"""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from repo_host_github_authority import authorize
from repo_host_github_integration import (
  IntegrationProviderError, create_int_attempt, inventory_ready_refs,
  cas_int_attempt_git,
)
from repo_host_github_provider import GitHubBackend, ProviderError
from repo_host_github_integration_terminal import (
  read_terminal, record_terminal,
)
from repo_host_github_integration_lease import read_lease, cas_lease


_OPERATIONS = {
  "refs.list", "ref.create", "ref.cas",
  "attempt.read", "attempt.record", "lease.read", "lease.cas",
}


def process(request, *, backend_factory=GitHubBackend, verify=authorize,
            cas_write=cas_int_attempt_git, config_reader=None,
            terminal_read=read_terminal, terminal_write=record_terminal,
            verify_terminal_evidence=None,
            lease_read=read_lease, lease_write=cas_lease):
  """Run only implemented provider operations after strict v2 validation."""
  if (type(request) is not dict or set(request) != {
      "schema_version", "repository", "operation",
      "request_id", "parameters"}):
    raise IntegrationProviderError("invalid v2 request envelope")
  operation = request["operation"]
  if operation not in _OPERATIONS:
    raise IntegrationProviderError("unsupported v2 provider operation")
  # Validate the request through the exact same boundary used by callers,
  # without invoking a privileged mutation.
  from repo_workflow.integration_host_v2 import IntegrationHost, IntegrationHostError
  def execute(value):
    backend = backend_factory(value["repository"])
    params = value["parameters"]
    if operation == "refs.list":
      return "unchanged", {"refs": inventory_ready_refs(backend)}
    if operation == "attempt.read":
      guid = params["guid"]
      return "unchanged", {
        "guid": guid, "record": terminal_read(backend, guid),
      }
    if operation == "lease.read":
      return "unchanged", lease_read(backend, params["destination"])
    try:
      decision = verify(value, backend)
    except Exception as error:
      raise IntegrationHostError("trusted authorization denied") from error
    if not isinstance(decision, dict):
      raise IntegrationHostError("trusted authorization proof missing")
    if operation == "attempt.record":
      if verify_terminal_evidence is None:
        raise IntegrationHostError("trusted terminal verifier unavailable")
      return terminal_write(
        backend, params["record"], authorized=True,
        verify_evidence=verify_terminal_evidence,
      )
    if operation in {"ref.cas", "lease.cas"}:
      root = Path(__file__).resolve().parents[1]
      if config_reader is None:
        from repo_workflow.config import load_config
        config = load_config(root)
      else:
        config = config_reader(root)
      remote = config["repository"]["authoritativeRemote"]
      if operation == "lease.cas":
        return lease_write(backend, value, root, remote)
      return "applied", cas_write(
        root, remote, params["ref"], params["expected_sha"], params["sha"])
    return create_int_attempt(backend, value, authorized=True)

  state = {}
  def transport(value):
    status, result = execute(value)
    state['status'] = status
    return {
      "schema_version": 2, "repository": value["repository"],
      "operation": value["operation"], "request_id": value["request_id"],
      "status": status, "result": result,
    }
  host = IntegrationHost(request.get("repository"), transport)
  result = host.request(
    operation, request.get("request_id"), request.get("parameters"))
  return transport_response(request, result, operation, state['status'])


def transport_response(request, result, operation, status):
  return {
    "schema_version": 2, "repository": request["repository"],
    "operation": operation, "request_id": request["request_id"],
    "status": status,
    "result": result,
  }


def main():
  try:
    raw = sys.stdin.read(1048577)
    if len(raw) > 1048576:
      raise IntegrationProviderError("request too large")
    request = json.loads(raw)
    response = process(request)
  except (ValueError, TypeError, ProviderError,
          IntegrationProviderError, Exception):
    # Never display untrusted provider payload or credentials.
    print("integration-host v2 outcome unavailable", file=sys.stderr)
    return 1
  print(json.dumps(response, sort_keys=True))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
