from __future__ import annotations

from pathlib import Path

from .repo_info_adapter import issue_info, list_open_issues, resolve_info_config


def show_issue_info(root: Path, argument: str | None) -> list[str]:
  config = resolve_info_config(root)
  if argument is None:
    value = list_open_issues(root, config)
    return [
      f"#{item['number']}  {item['title']}"
      for item in value["issues"]
    ]

  if not argument.isdecimal() or int(argument) <= 0:
    raise ValueError(f"invalid issue number: {argument}")
  value = issue_info(root, config, int(argument))
  return [
    f"#{value['number']}  {value['title']}  {value['state']}  {value['link']}"
  ]
