"""Canonical #572 PASS terminal identities for qualified READY submissions."""
import re

from .phase_terminal import PhaseTransitionError, plan_phase


_TEST_VERSION = re.compile(
  r"[0-9]+\.[0-9]+\.[0-9]+-issue\.([1-9][0-9]*)\.[0-9]+\.[1-9][0-9]*\Z"
)


def expected_v2_terminal_tags(version: str, issue: str) -> dict[str, str]:
  """Bind both terminal phases to the same exact ticket version."""
  if (type(version) is not str or type(issue) is not str
      or re.fullmatch(r"[1-9][0-9]*", issue) is None):
    raise ValueError("invalid hosted terminal identity")
  match = _TEST_VERSION.fullmatch(version)
  if match is None or match.group(1) != issue:
    raise ValueError("hosted terminal version is not ticket-qualified")
  try:
    regression = plan_phase(
      version, phase="regression", outcome="PASS").terminal_tag
    integration = plan_phase(
      version, phase="integration", outcome="PASS").terminal_tag
  except PhaseTransitionError as error:
    raise ValueError("invalid hosted terminal version") from error
  assert regression is not None
  assert integration is not None
  return {"regression": regression, "integration": integration}
