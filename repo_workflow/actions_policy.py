from __future__ import annotations

from pathlib import Path


class ActionsPolicyError(RuntimeError):
  pass


def check_actions_policy(
  root: Path,
  engine_root: Path,
  *,
  migration_workflows: list[str] | None = None,
) -> None:
  workflows = root / ".github" / "workflows"
  canonical = engine_root / "templates" / "github" / "ci.yml"
  if not canonical.is_file():
    raise ActionsPolicyError(f"canonical GitHub adapter is missing: {canonical}")
  if not workflows.is_dir():
    raise ActionsPolicyError(".github/workflows is missing")
  files = sorted(
    path.relative_to(workflows).as_posix()
    for path in workflows.rglob("*")
    if path.is_file()
  )
  expected = sorted(["ci.yml", *(migration_workflows or [])])
  if files != expected:
    raise ActionsPolicyError(
      "consumer workflow set must match canonical adapter plus declared migration "
      "workflows; expected: " + ", ".join(expected) + "; found: " + ", ".join(files)
    )
  consumer = workflows / "ci.yml"
  if consumer.read_bytes() != canonical.read_bytes():
    raise ActionsPolicyError(
      ".github/workflows/ci.yml does not match the pinned RepoWorkflow adapter"
    )
