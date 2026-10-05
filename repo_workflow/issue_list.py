from __future__ import annotations

from pathlib import Path

from .repo_info_adapter import issue_info, list_open_issues, resolve_info_config


def _arguments(arguments: list[str]) -> tuple[list[int], bool]:
  if not arguments:
    return [], False

  links = arguments[-1] == "--links"
  values = arguments[:-1] if links else arguments
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
  config = resolve_info_config(root)
  lines: list[str] = []

  if not issues:
    listed = list_open_issues(root, config)["issues"]
    if not links:
      return [f"#{item['number']}  {item['title']}" for item in listed]
    issues = [int(item["number"]) for item in listed]

  for number in issues:
    value = issue_info(root, config, number)
    line = f"#{value['number']}  {value['title']}"
    if links:
      line += f"  {value['link']}"
    lines.append(line)
  return lines
