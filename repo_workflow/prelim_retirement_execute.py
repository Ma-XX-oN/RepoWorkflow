"""Execute an exact-ref retirement after fresh provider-backed proof.

The preflight and mutation remain separate safety boundaries. This
orchestrator never deletes another submission or assumes a GREEN test
proves landing.
"""
from pathlib import Path

from .prelim_retirement import (
  LandedIntegration, PrelimRetirementError,
)
from .prelim_retirement_github import verify_github_retirement
from .prelim_retirement_remote import (
  RefRetirement, retire_verified_ref,
)


def retire_landed_attempt_ref(
    *, root: Path, remote: str, backend,
    landed: LandedIntegration, read_terminal, ref_kind: str,
) -> RefRetirement:
  """Refresh landing and durable evidence immediately before conditional push."""
  if not isinstance(landed, LandedIntegration):
    raise PrelimRetirementError("landing provenance required")
  if ref_kind not in {"PRELIM", "INT-ATTEMPT"}:
    raise PrelimRetirementError("unsupported attempted ref kind")
  plan = verify_github_retirement(backend, landed, read_terminal)
  ref = landed.prelim_ref if ref_kind == "PRELIM" else landed.int_attempt_ref
  old_sha = landed.prelim_sha if ref_kind == "PRELIM" else landed.accepted_sha
  # The provider proof validates the integrated candidate; git push uses
  # --force-with-lease for an atomic expected-old ref comparison.
  return retire_verified_ref(root, remote, plan, ref, old_sha, backend=backend)
