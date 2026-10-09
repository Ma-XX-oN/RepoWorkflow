"""Pure task regression / preliminary integration terminal lifecycle.

No Git refs, VERSION files, or evidence are mutated here. A4 validates the
canonical provider result and exact candidate before applying these plans.
"""
from __future__ import annotations

from dataclasses import dataclass
import re


_VERSION = re.compile(
  r"(?P<base>[0-9]+\.[0-9]+\.[0-9]+)-issue\."
  r"(?P<issue>[1-9][0-9]*)\.(?P<q>[0-9]+)\.(?P<r>[1-9][0-9]*)"
)
_TERMINAL = {"PASS", "FAIL", "INCOMPLETE"}
_PHASES = {"regression", "integration"}


class PhaseTransitionError(ValueError):
  pass


@dataclass(frozen=True)
class PhasePlan:
  phase: str
  outcome: str
  current_version: str
  terminal_tag: str | None
  next_version: str
  next_request: tuple[str, ...] | None


def plan_phase(
  version: str, *, phase: str, outcome: str,
  prior_terminal: str | None = None,
) -> PhasePlan:
  """Derive distinct immutable tag identity and next semantic request.

  next_request is an adapter operation for the *next* attempt, not a
  mutation permitted during terminal evidence creation.
  """
  if prior_terminal is not None and prior_terminal not in {"PASS", "FAIL"}:
    raise PhaseTransitionError("invalid prior terminal state")
  if prior_terminal is not None and (
    outcome == "INCOMPLETE" or outcome != prior_terminal
  ):
    raise PhaseTransitionError("terminal outcome is already immutable")
  match = _VERSION.fullmatch(version)
  if match is None:
    raise PhaseTransitionError("invalid task development version")
  if phase not in _PHASES:
    raise PhaseTransitionError("only regression and integration are terminal")
  if outcome not in _TERMINAL:
    raise PhaseTransitionError("invalid terminal outcome")
  components = (*match.group("base").split("."), match.group("issue"),\n                match.group("q"), match.group("r"))\n  if any(len(item) > 1 and item.startswith("0") for item in components):\n    raise PhaseTransitionError("noncanonical numeric version component")\n  base = match.group("base")
  issue = int(match.group("issue"))
  q = int(match.group("q"))
  r = int(match.group("r"))
  request = None
  next_version = version
  tag = None
  if outcome != "INCOMPLETE":
    if phase == "regression":
      tag = "v" + version
    else:
      tag = f"v{base}-PRELIM-{issue}.{q}.{r}"
    if outcome == "FAIL":
      # Existing CI-FAIL outcome suffix, composed with the PRELIM namespace.
      tag += "-CI-FAIL"
      if phase == "regression":
        request = ("task", "--increment", "CI-iteration")
        next_version = f"{base}-issue.{issue}.{q}.{r + 1}"
      else:
        request = ("task", "--increment", "merge-integration-failed")
        next_version = f"{base}-issue.{issue}.{q + 1}.1"
  return PhasePlan(phase, outcome, version, tag, next_version, request)
