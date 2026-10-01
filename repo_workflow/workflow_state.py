from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Iterable

from .branch_policy import BranchPolicyError, check_branch_policy
from .config import load_config
from .git import current_branch, head_sha
from .prelim import PRELIM_BRANCH, PrelimError, prelim_status
from .version_adapter import VersionAdapterError, read_version


REGRESSION_STATUSES = {"missing", "PASS", "FAIL", "INCOMPLETE"}
INTEGRATION_STATUSES = {None, "succeeded", "failed"}


@dataclass(frozen=True)
class WorkflowFacts:
  branch_valid: bool = True
  version_valid: bool = True
  regression: str = "missing"
  integration_result: str | None = None
  integration_authorized: bool = False
  prelim_present: bool = False
  prelim_base_current: bool | None = True

  def __post_init__(self) -> None:
    if self.regression not in REGRESSION_STATUSES:
      raise ValueError(f"invalid regression status: {self.regression}")
    if self.integration_result not in INTEGRATION_STATUSES:
      raise ValueError(f"invalid integration result: {self.integration_result}")


@dataclass(frozen=True)
class WorkflowPlan:
  transitions: tuple[str, ...]
  blocks: tuple[str, ...]

  def to_json_value(self) -> dict:
    return {
      "transitions": list(self.transitions),
      "blocks": list(self.blocks),
    }


def derive_plan(facts: WorkflowFacts) -> WorkflowPlan:
  transitions: list[str] = []
  blocks: list[str] = []

  if not facts.branch_valid:
    blocks.append("invalid branch state")
  if not facts.version_valid:
    blocks.append("invalid version state")
  if blocks:
    return WorkflowPlan(tuple(transitions), tuple(blocks))

  if facts.prelim_present and facts.prelim_base_current is not True:
    transitions.append("reintegrate")
    blocks.append("merge/integration blocked: stale integration base")
    return WorkflowPlan(tuple(transitions), tuple(blocks))

  if facts.regression == "missing":
    transitions.append("validate regression")
    blocks.append("integration blocked: missing regression validation")
    return WorkflowPlan(tuple(transitions), tuple(blocks))

  if facts.regression == "INCOMPLETE":
    transitions.append("validate regression")
    blocks.append("integration blocked: regression validation incomplete")
    return WorkflowPlan(tuple(transitions), tuple(blocks))

  if facts.regression == "FAIL":
    transitions.append("validate regression")
    blocks.append("integration blocked: regression validation failed")
    return WorkflowPlan(tuple(transitions), tuple(blocks))

  if facts.integration_result is None:
    transitions.extend((
      "validate integration succeeded",
      "validate integration failed",
    ))
    blocks.append("merge/integration blocked: integration result required")
    return WorkflowPlan(tuple(transitions), tuple(blocks))

  if facts.integration_result == "failed":
    transitions.append("validate regression")
    blocks.append("integration blocked: previous integration failed")
    return WorkflowPlan(tuple(transitions), tuple(blocks))

  if not facts.integration_authorized:
    blocks.append("merge/integration blocked: explicit authorization absent")
  else:
    transitions.append("integrate")
  return WorkflowPlan(tuple(transitions), tuple(blocks))


def completion_candidates(plan: WorkflowPlan, words: Iterable[str]) -> list[str]:
  tokens = list(words)
  if not tokens:
    tokens = [""]
  prefix = tokens[-1]
  completed = tokens[:-1]

  commands = ["init", "what-next", *plan.transitions]
  candidates: set[str] = set()
  for command in commands:
    command_tokens = command.split()
    if len(completed) >= len(command_tokens):
      continue
    if command_tokens[:len(completed)] != completed:
      continue
    candidate = command_tokens[len(completed)]
    if candidate.startswith(prefix):
      candidates.add(candidate)

  if completed == ["what-next"] and "--json".startswith(prefix):
    candidates.add("--json")
  if completed == ["init"]:
    for option in ("--bash", "--force"):
      if option.startswith(prefix):
        candidates.add(option)
  return sorted(candidates)


def _git_dir(root: Path) -> Path:
  dot_git = root / ".git"
  if dot_git.is_dir():
    return dot_git
  if dot_git.is_file():
    text = dot_git.read_text(encoding="utf-8").strip()
    prefix = "gitdir: "
    if text.startswith(prefix):
      path = Path(text[len(prefix):])
      return path if path.is_absolute() else (root / path).resolve()
  raise ValueError("cannot locate repository Git directory")


def _cache_path(root: Path) -> Path:
  return _git_dir(root) / "repoworkflow" / "state.json"


def load_local_state(root: Path, candidate_sha: str) -> dict:
  path = _cache_path(root)
  try:
    value = json.loads(path.read_text(encoding="utf-8"))
  except (FileNotFoundError, json.JSONDecodeError):
    return {}
  if not isinstance(value, dict) or value.get("candidate") != candidate_sha:
    return {}
  return value


def save_local_state(root: Path, candidate_sha: str, **updates) -> None:
  path = _cache_path(root)
  path.parent.mkdir(parents=True, exist_ok=True)
  current = load_local_state(root, candidate_sha)
  current.update(updates)
  current["candidate"] = candidate_sha
  path.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def discover_facts(root: Path) -> WorkflowFacts:
  root = root.resolve()
  config = load_config(root)
  branch = current_branch(root)
  branch_valid = branch != "HEAD"
  prelim_present = False
  prelim_base_current: bool | None = True

  if branch_valid and branch == PRELIM_BRANCH:
    try:
      status = prelim_status(root, config)
      prelim_present = status.present
      prelim_base_current = status.current
      branch_valid = status.present
    except (PrelimError, ValueError):
      branch_valid = False
      prelim_base_current = None
  elif branch_valid:
    try:
      check_branch_policy(
        root,
        branch,
        None,
        config["repository"]["authoritativeRemote"],
      )
    except (BranchPolicyError, ValueError):
      branch_valid = False

  version_valid = True
  try:
    read_version(root, config)
  except (VersionAdapterError, ValueError):
    version_valid = False

  candidate = head_sha(root)
  state = load_local_state(root, candidate)
  regression = state.get("regression", "missing")
  if regression not in REGRESSION_STATUSES:
    regression = "missing"
  integration_result = state.get("integrationResult")
  if integration_result not in INTEGRATION_STATUSES:
    integration_result = None

  return WorkflowFacts(
    branch_valid=branch_valid,
    version_valid=version_valid,
    regression=regression,
    integration_result=integration_result,
    integration_authorized=False,
    prelim_present=prelim_present,
    prelim_base_current=prelim_base_current,
  )


def render_human(plan: WorkflowPlan) -> str:
  lines = ["Legal transitions:"]
  if plan.transitions:
    lines.extend(f"  {transition}" for transition in plan.transitions)
  else:
    lines.append("  (none)")
  lines.append("Blocked:")
  if plan.blocks:
    lines.extend(f"  {block}" for block in plan.blocks)
  else:
    lines.append("  (none)")
  return "\n".join(lines)
