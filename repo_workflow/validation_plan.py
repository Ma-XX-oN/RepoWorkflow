"""Core evidence-aware hosted validation planner (#110).

Planning consumes #70 authenticated import decisions; provider dispatch remains a
mechanics-only operation and must never grant a terminal validation verdict.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Literal

from .repo_ci_dispatcher import dispatch
from .validation_coverage import Requirement
from .validation_import import ImportDecision, import_from_store
from .validation_store import ValidationEvidenceStore


Action = Literal["reuse", "execute", "manual-required"]


class ValidationPlanError(ValueError):
  pass


@dataclass(frozen=True)
class PlannedUnit:
  unit: str
  mode: str
  action: Action
  evidence_status: str
  accepted_record_ids: tuple[str, ...]
  reason: str


@dataclass(frozen=True)
class HostedPlan:
  candidate_sha: str
  units: tuple[PlannedUnit, ...]

  @property
  def automated_units(self) -> tuple[str, ...]:
    return tuple(unit.unit for unit in self.units if unit.action == "execute")

  @property
  def manual_units(self) -> tuple[str, ...]:
    return tuple(unit.unit for unit in self.units if unit.action == "manual-required")

  @property
  def complete(self) -> bool:
    return all(unit.action == "reuse" for unit in self.units)


def build_plan(
  requirements: list[Requirement],
  decisions: tuple[ImportDecision, ...],
  candidate_sha: str,
) -> HostedPlan:
  """Decide work from independently authenticated importer results.

  This function cannot authenticate arbitrary caller-created decisions.
  Use plan_from_store as the external entrypoint for durable evidence.
  """
  if (not isinstance(candidate_sha, str)
      or len(candidate_sha) not in (40, 64)
      or any(c not in "0123456789abcdef" for c in candidate_sha)):
    raise ValidationPlanError("candidate must be an exact SHA")
  if not isinstance(requirements, list) or not all(
    isinstance(value, Requirement) for value in requirements
  ):
    raise ValidationPlanError("invalid required validation units")
  if not isinstance(decisions, tuple) or not all(
    isinstance(value, ImportDecision) for value in decisions
  ):
    raise ValidationPlanError("invalid imported evidence decisions")
  requirements_by_id = {value.unit: value for value in requirements}
  imported_by_id = {value.unit: value for value in decisions}
  if (len(requirements_by_id) != len(requirements)
      or len(imported_by_id) != len(decisions)
      or set(requirements_by_id) != set(imported_by_id)):
    raise ValidationPlanError("incomplete, duplicate, or extra evidence coverage")
  result = []
  for unit in sorted(requirements_by_id):
    required = requirements_by_id[unit]
    decision = imported_by_id[unit]
    if decision.status not in ("applicable", "stale", "missing", "unusable"):
      raise ValidationPlanError("invalid evidence classification")
    if decision.status == "applicable":
      if not decision.accepted_record_ids:
        raise ValidationPlanError("applicable evidence requires authenticated records")
      action: Action = "reuse"
    elif required.mode == "manual":
      action = "manual-required"
    else:
      action = "execute"
    if decision.status != "applicable" and decision.accepted_record_ids:
      raise ValidationPlanError("unusable evidence cannot be accepted")
    result.append(PlannedUnit(
      unit, required.mode, action, decision.status,
      decision.accepted_record_ids, decision.reason,
    ))
  return HostedPlan(candidate_sha, tuple(result))


def plan_from_store(
  store: ValidationEvidenceStore,
  requirements: list[Requirement],
  candidate_sha: str,
  *,
  trusted_record_ids: frozenset[str],
  equivalent_candidate_shas: frozenset[str],
) -> HostedPlan:
  """Read checked durable evidence, classify applicability, and plan missing work."""
  if not isinstance(store, ValidationEvidenceStore):
    raise ValidationPlanError("durable evidence store required")
  decisions = import_from_store(
    store, requirements, candidate_sha,
    trusted_record_ids=trusted_record_ids,
    equivalent_candidate_shas=equivalent_candidate_shas,
  )
  return build_plan(requirements, decisions, candidate_sha)


def dispatch_missing(
  root: Path,
  plan: HostedPlan,
  request: dict,
  groups: dict[str, str],
) -> dict:
  """Dispatch only missing automated groups and verify provider observations.

  Zero automated units produce no provider invocation. The caller retains
  ownership of classification and of all manual/MIT requirements.
  """
  if not isinstance(plan, HostedPlan):
    raise ValidationPlanError("a verified hosted plan is required")
  if not isinstance(request, dict) or not isinstance(groups, dict):
    raise ValidationPlanError("provider request and group catalogue required")
  candidate = request.get("candidate")
  if not isinstance(candidate, dict) or candidate.get("commit") != plan.candidate_sha:
    raise ValidationPlanError("provider candidate does not match plan")
  if set(request) != {
    "contract_version", "operation", "invocation_id", "candidate",
    "requirements", "inputs",
  } or request["contract_version"] != 1 or request["operation"] != "execute":
    raise ValidationPlanError("invalid provider request envelope")
  if not isinstance(request["requirements"], dict) or (
    request["requirements"].get("capabilities") != []
    or request["requirements"].get("artifacts") != []
  ):
    raise ValidationPlanError("unexpected provider requirements")
  if not isinstance(request["inputs"], dict):
    raise ValidationPlanError("missing provider inputs")
  base = request["inputs"].get("base")
  if not isinstance(base, str) or base != candidate.get("base"):
    raise ValidationPlanError("base identity mismatch")
  if set(groups) != set(plan.automated_units) or not all(
    isinstance(name, str) and name for name in groups.values()
  ):
    raise ValidationPlanError("catalogue must cover only missing automated units")
  if not plan.automated_units:
    return {"executed": (), "observations": (), "reused": tuple(
      unit.unit for unit in plan.units if unit.action == "reuse"
    ), "manual_pending": plan.manual_units}
  outbound = {
    **request,
    "requirements": {
      **request["requirements"], "stages": list(plan.automated_units),
    },
    "inputs": {"base": base, "stage_groups": dict(groups)},
  }
  response = dispatch(Path(root), "execute", json.dumps(
    outbound, separators=(",", ":")
  ).encode("utf-8"))
  if response.get("status") != "ok" or response.get("candidate") != candidate:
    raise ValidationPlanError("provider execution or candidate verification failed")
  stages = response.get("observations", {}).get("stages")
  if not isinstance(stages, list) or len(stages) != len(plan.automated_units):
    raise ValidationPlanError("provider stage observation set is incomplete")
  observed: dict[str, dict] = {}
  for stage in stages:
    if not isinstance(stage, dict) or (
      stage.get("stage") not in plan.automated_units
      or stage.get("stage") in observed
      or stage.get("candidate") != candidate
      or type(stage.get("complete")) is not bool
      or stage.get("outcome") not in ("succeeded", "failed", "unavailable")
    ):
      raise ValidationPlanError("invalid or duplicate provider observation")
    if stage["outcome"] == "unavailable" and stage["complete"]:
      raise ValidationPlanError("unavailable stage must be incomplete")
    if stage["outcome"] != "unavailable" and not stage["complete"]:
      raise ValidationPlanError("inconsistent provider completeness")
    observed[stage["stage"]] = stage
  if set(observed) != set(plan.automated_units):
    raise ValidationPlanError("required provider stage missing")
  return {
    "executed": plan.automated_units,
    "observations": tuple(observed[unit] for unit in plan.automated_units),
    "reused": tuple(unit.unit for unit in plan.units if unit.action == "reuse"),
    "manual_pending": plan.manual_units,
  }
