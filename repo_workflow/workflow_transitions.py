from __future__ import annotations

from pathlib import Path

from .config import load_config
from .git import changed_files, git, head_sha, repository_state, restore_repository_state
from .local import verify_local
from .validation_classes import run_validation_class
from .version_adapter import read_development_version, run_transition
from .workflow_state import derive_plan, discover_facts, save_local_state


def _require_transition(root: Path, transition: str) -> None:
  plan = derive_plan(discover_facts(root))
  if transition not in plan.transitions:
    detail = "; ".join(plan.blocks) if plan.blocks else "transition is not legal"
    raise ValueError(f"{transition} is blocked: {detail}")


def _write_request(root: Path, version: str) -> None:
  path = root / ".ci" / "run-ci-request"
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(version + "\n", encoding="utf-8")


def _commit_bookkeeping(root: Path, message: str) -> str:
  paths = changed_files(root)
  if not paths:
    raise ValueError("workflow transition produced no bookkeeping changes")
  git(root, "add", "--all")
  git(root, "commit", "-m", message)
  return head_sha(root)


def _record_integration_failure(root: Path) -> str:
  before = repository_state(root)
  try:
    config = load_config(root)
    run_transition(
      root,
      config,
      "task",
      "--increment",
      "merge-integration-failed",
    )
    version = read_development_version(root, config)
    _write_request(root, version)
    candidate = _commit_bookkeeping(
      root,
      f"chore(workflow): advance integration generation to {version}",
    )
    save_local_state(
      root,
      candidate,
      regression="missing",
      automaticIntegration="FAIL",
      manualIntegrationResult=None,
      integrationResult="failed",
    )
    return candidate
  except Exception:
    restore_repository_state(root, before)
    raise


def validate_regression(
  root: Path,
  *,
  engine_root: Path,
  fast: bool = False,
  group: str | None = None,
) -> str:
  root = root.resolve()
  if fast or group is not None:
    facts = discover_facts(root)
    if not facts.branch_valid or not facts.version_valid:
      raise ValueError("diagnostic regression validation requires valid repository state")
    return run_validation_class(root, "ART", fast=fast, group=group)

  _require_transition(root, "validate regression")
  outcome = verify_local(root, engine_root=engine_root, push=False)
  candidate = head_sha(root)
  save_local_state(
    root,
    candidate,
    regression=outcome,
    automaticIntegration="missing",
    manualIntegrationResult=None,
    integrationResult=None,
  )
  if outcome != "FAIL":
    return outcome

  before = repository_state(root)
  try:
    config = load_config(root)
    run_transition(root, config, "task", "--increment", "CI-iteration")
    version = read_development_version(root, config)
    _write_request(root, version)
    candidate = _commit_bookkeeping(
      root,
      f"chore(workflow): advance regression iteration to {version}",
    )
    save_local_state(
      root,
      candidate,
      regression="missing",
      automaticIntegration="missing",
      manualIntegrationResult=None,
      integrationResult=None,
    )
  except Exception:
    restore_repository_state(root, before)
    raise
  return outcome


def validate_automatic_integration(
  root: Path,
  *,
  group: str | None = None,
) -> str:
  root = root.resolve()
  if group is not None:
    facts = discover_facts(root)
    if facts.regression != "PASS":
      raise ValueError("integration group validation requires complete ART PASS")
    return run_validation_class(root, "AIT", group=group)

  _require_transition(root, "validate integration")
  outcome = run_validation_class(root, "AIT")
  candidate = head_sha(root)
  if outcome == "PASS":
    save_local_state(
      root,
      candidate,
      automaticIntegration="PASS",
      manualIntegrationResult=None,
      integrationResult=None,
    )
    return outcome
  if outcome == "INCOMPLETE":
    save_local_state(
      root,
      candidate,
      automaticIntegration="INCOMPLETE",
      manualIntegrationResult=None,
      integrationResult=None,
    )
    return outcome

  _record_integration_failure(root)
  return outcome


def require_manual_integration(root: Path) -> None:
  facts = discover_facts(root)
  plan = derive_plan(facts)
  expected = {
    "validate integration succeeded",
    "validate integration failed",
  }
  if not expected.issubset(set(plan.transitions)):
    detail = "; ".join(plan.blocks) if plan.blocks else "manual integration is not pending"
    raise ValueError(f"manual integration is blocked: {detail}")


def validate_integration(root: Path, result: str) -> str:
  root = root.resolve()
  if result not in {"succeeded", "failed"}:
    raise ValueError(f"invalid integration result: {result}")
  _require_transition(root, f"validate integration {result}")

  candidate = head_sha(root)
  if result == "succeeded":
    save_local_state(
      root,
      candidate,
      manualIntegrationResult="succeeded",
      integrationResult="succeeded",
    )
    return candidate

  return _record_integration_failure(root)
