"""Project a fully verified provider terminal record for #103 retirement.

The provider record is the sole authority.  A nine-field record supplied by
a caller is never accepted as a substitute for provider readback.
"""
from dataclasses import dataclass
import re

from .integration_host_v2 import IntegrationHost, IntegrationHostError
from .prelim_retirement import LandedIntegration, PrelimRetirementError
from .prelim_retirement import verify_attempt_scope


@dataclass(frozen=True)
class VerifiedTerminalReader:
  """Callable read_terminal callback for #103's exact evidence verifier."""
  host: IntegrationHost
  landed: LandedIntegration
  request_id: str

  def __call__(self, evidence_ref: str) -> dict:
    if not isinstance(self.host, IntegrationHost):
      raise PrelimRetirementError("authenticated integration host required")
    if not isinstance(self.landed, LandedIntegration):
      raise PrelimRetirementError("provider landing identity required")
    if evidence_ref != self.landed.terminal_evidence_ref:
      raise PrelimRetirementError("terminal evidence request differs")
    verify_attempt_scope(
      self.landed.prelim_ref, self.landed.int_attempt_ref,
      self.landed.destination_ref)
    match = re.search(r"-([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})\Z",
                      self.landed.prelim_ref)
    if match is None:
      raise PrelimRetirementError("immutable PRELIM GUID unavailable")
    guid = match.group(1)
    if not self.landed.int_attempt_ref.endswith("-" + guid):
      raise PrelimRetirementError("integration attempt GUID differs")
    try:
      reply = self.host.request(
        "attempt.read", self.request_id, {"guid": guid})
    except IntegrationHostError as error:
      raise PrelimRetirementError(
        "authenticated terminal provider read UNKNOWN") from error
    full = reply["record"]
    if full is None or full["status"] != "integrated":
      raise PrelimRetirementError("provider has no integrated terminal")
    required = {
      "prelim_ref": self.landed.prelim_ref,
      "prelim_sha": self.landed.prelim_sha,
      "int_attempt_ref": self.landed.int_attempt_ref,
      "accepted_sha": self.landed.accepted_sha,
      "destination_ref": self.landed.destination_ref,
      "landed_sha": self.landed.landed_sha,
      "integration_id": self.landed.integration_id,
      "terminal_evidence_ref": self.landed.terminal_evidence_ref,
    }
    if any(full[k] != value for k, value in required.items()):
      raise PrelimRetirementError("provider terminal identity mismatch")
    # IntegrationHost validates all fifteen mandatory terminal fields,
    # repository identity, provider operation and PRELIM/INT scope before
    # this exact #103 projection is returned.  The full record remains
    # provider-owned and is never rewritten to satisfy the old interface.
    return {"status": "integrated", **required}
