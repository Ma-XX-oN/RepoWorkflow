from __future__ import annotations

from pathlib import Path

from .config import load_config
from .git import changed_files, git, head_sha, repository_state, restore_repository_state
from .local import verify_local
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


def validate_regression(root: Path, *, engine_root: Path) -> str:
  root = root.resolve()
  _require_transition(root, "validate regression")
  outcome = verify_local(root, engine_root=engine_root, push=False)
  candidate = head_sha(root)
  save_local_state(root, candidate, regression=outcome, integrationResult=None)
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
    save_local_state(root, candidate, regression="missing", integrationResult=None)
  except Exception:
    restore_repository_state(root, before)
    raise
  return outcome


def validate_integration(root: Path, result: str) -> str:
  root = root.resolve()
  if result not in {"succeeded", "failed"}:
    raise ValueError(f"invalid integration result: {result}")
  _require_transition(root, f"validate integration {result}")

  candidate = head_sha(root)
  if result == "succeeded":
    save_local_state(root, candidate, integrationResult="succeeded")
    return candidate

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
      integrationResult="failed",
    )
    return candidate
  except Exception:
    restore_repository_state(root, before)
    raise
