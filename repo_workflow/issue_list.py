from __future__ import annotations

from pathlib import Path

from .config import load_config
from .repo_info_adapter import issue_info


def _arguments(arguments: list[str]) -> tuple[list[int], bool]:
  if not arguments:
    raise ValueError("issue list requires at least one issue number")

  links = arguments[-1] == "--links"
  values = arguments[:-1] if links else arguments
  if not values:
    raise ValueError("issue list requires at least one issue number")
  if "--links" in values:
    raise ValueError("--links must follow all issue numbers")

  issues: list[int] = []
  for value in values:
    if not value.isdecimal() or int(value) <= 0:
      raise ValueError(f"invalid issue number: {value}")
    issues.append(int(value))
  return issues, links


def list_issues(root: Path, arguments: list[str]) -> list[str]:
  issues, links = _arguments(arguments)
  config = load_config(root)
  lines: list[str] = []
  for number in issues:
    value = issue_info(root, config, number)
    line = f"#{value['number']}  {value['title']}"
    if links:
      line += f"  {value['link']}"
    lines.append(line)
  return lines
