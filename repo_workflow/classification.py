from __future__ import annotations

import fnmatch
import json
from pathlib import Path
import subprocess
from typing import Any


class ClassificationError(RuntimeError):
  pass


def load_change_classes(root: Path) -> dict[str, dict[str, Any]]:
  path = root / ".repoworkflow" / "change-classes.json"
  try:
    data = json.loads(path.read_text(encoding="utf-8"))
  except FileNotFoundError as exc:
    raise ClassificationError(f"missing change-class policy: {path}") from exc
  except json.JSONDecodeError as exc:
    raise ClassificationError(f"invalid JSON in {path}: {exc}") from exc
  if not isinstance(data, dict) or data.get("schema") != 1:
    raise ClassificationError("change-classes.json must declare schema 1")
  if set(data) != {"schema", "classes"} or not isinstance(data["classes"], dict):
    raise ClassificationError("change-classes.json must contain only schema and classes")
  result: dict[str, dict[str, Any]] = {}
  for name, value in data["classes"].items():
    if not isinstance(name, str) or not name or not isinstance(value, dict):
      raise ClassificationError("each change class must be a named object")
    if set(value) != {"paths", "validation"}:
      raise ClassificationError(
        f"{name} must contain exactly paths and validation"
      )
    paths = value["paths"]
    validation = value["validation"]
    if (
      not isinstance(paths, list)
      or not paths
      or not all(isinstance(item, str) and item for item in paths)
    ):
      raise ClassificationError(f"{name}.paths must be non-empty strings")
    if not isinstance(validation, str) or not validation:
      raise ClassificationError(f"{name}.validation must be a non-empty string")
    result[name] = {"paths": list(paths), "validation": validation}
  return result


def _matches(path: str, pattern: str) -> bool:
  path = path.replace("\\", "/")
  pattern = pattern.replace("\\", "/")
  if pattern.startswith("**/") and fnmatch.fnmatchcase(path, pattern[3:]):
    return True
  return fnmatch.fnmatchcase(path, pattern)


def classify_paths(
  paths: list[str],
  classes: dict[str, dict[str, Any]],
) -> tuple[str | None, str]:
  normalized = [path.replace("\\", "/") for path in paths]
  for name, policy in classes.items():
    if normalized and all(
      any(_matches(path, pattern) for pattern in policy["paths"])
      for path in normalized
    ):
      return name, policy["validation"]
  return None, "full"


def changed_paths(root: Path, base: str, head: str = "HEAD") -> list[str]:
  completed = subprocess.run(
    ["git", "diff", "--name-only", "-z", base, head],
    cwd=root,
    check=False,
    capture_output=True,
  )
  if completed.returncode:
    stderr = completed.stderr.decode(errors="replace").strip()
    raise ClassificationError(f"cannot determine changed files: {stderr}")
  return sorted(
    item.decode(errors="surrogateescape")
    for item in completed.stdout.split(b"\0")
    if item
  )
