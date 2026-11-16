from __future__ import annotations

from pathlib import Path

from .git import head_sha
from .local import verify_local
from .workflow_state import discover_facts, save_local_state


def validate_regression(root: Path, *, engine_root: Path) -> str:
  root = root.resolve()
  outcome = verify_local(root, engine_root=engine_root, push=False)
  candidate = head_sha(root)
  save_local_state(root, candidate, regression=outcome, integrationResult=None)
  return outcome


def validate_integration(root: Path, result: str) -> str:
  root = root.resolve()
  if result not in {"succeeded", "failed"}:
    raise ValueError(f"invalid integration result: {result}")
  facts = discover_facts(root)
  if facts.regression != "PASS":
    raise ValueError("integration result requires regression PASS for the exact candidate")

  candidate = head_sha(root)
  if result == "succeeded":
    save_local_state(root, candidate, integrationResult="succeeded")
    return candidate

  save_local_state(root, candidate, integrationResult="failed")
  return candidate
