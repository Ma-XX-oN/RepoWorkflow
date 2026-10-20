"""Bridge #681 immutable terminal ledger into certified #103 retirement proof.

The provider-backed reader returns the exact #103 terminal projection only
after comparing the complete independently persisted #681 terminal record.
"""
from dataclasses import dataclass

from .done_terminal_v2 import IntegratedTerminal
from .prelim_retirement import LandedIntegration


class RetirementBridgeError(RuntimeError):
  """Cross-provider terminal identity cannot authorize scoped cleanup."""


@dataclass(frozen=True)
class RetirementBridge:
  landed: LandedIntegration
  read_terminal: object


def retirement_bridge_from_v2(host, terminal: IntegratedTerminal):
  if (not isinstance(terminal, IntegratedTerminal)
      or terminal.repository != getattr(host, "repository", None)
      or not callable(getattr(host, "request", None))
      or type(terminal.record) is not dict):
    raise RetirementBridgeError("authenticated exact terminal is required")
  record = terminal.record
  if (record.get("status") != "integrated"
      or record.get("guid") != terminal.guid
      or record.get("repository") != terminal.repository
      or record.get("landed_sha") != terminal.landed_sha
      or record.get("accepted_sha") != terminal.accepted_sha
      or record.get("provider_operation_id") != terminal.operation_id
      or record.get("integration_id") != terminal.integration_id
      or record.get("terminal_evidence_ref") != terminal.terminal_evidence_ref):
    raise RetirementBridgeError("stored terminal does not match landing")
  landed = LandedIntegration(
    record["prelim_ref"], record["prelim_sha"],
    record["int_attempt_ref"], record["accepted_sha"],
    record["destination_ref"], record["landed_sha"],
    record["integration_id"], record["terminal_evidence_ref"],
  )
  counter = 0

  def read_terminal(evidence_ref):
    nonlocal counter
    if evidence_ref != terminal.terminal_evidence_ref:
      raise RetirementBridgeError("foreign terminal evidence reference")
    counter += 1
    result = host.request("attempt.read",
                          "retirement-terminal-" + terminal.guid + "-" +
                          str(counter), {"guid": terminal.guid})
    if (type(result) is not dict
        or result.get("guid") != terminal.guid
        or result.get("record") != record):
      raise RetirementBridgeError("terminal provider readback differs")
    keys = (
      "status", "prelim_ref", "prelim_sha",
      "int_attempt_ref", "accepted_sha", "destination_ref",
      "landed_sha", "integration_id", "terminal_evidence_ref",
    )
    return {key: record[key] for key in keys}

  return RetirementBridge(landed, read_terminal)
