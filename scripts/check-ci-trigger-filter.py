"""Static fail-closed gate for an on-demand GitHub Actions push trigger."""
from __future__ import annotations

import argparse
from pathlib import Path
import re


class TriggerFilterError(ValueError):
  pass


def extract_push_filters(text):
  """Read a deliberately restricted YAML push-filter subset."""
  lines = text.splitlines()
  if not any(line == "on:" for line in lines):
    raise TriggerFilterError("missing top-level on mapping")
  on_start = lines.index("on:") + 1
  block = []
  for line in lines[on_start:]:
    if line and not line.startswith((" ", "#")):
      break
    block.append(line)
  if not any(re.fullmatch(r"  push:", line) for line in block):
    raise TriggerFilterError("missing push trigger")
  forbidden = ("  pull_request:", "  workflow_dispatch:", "  schedule:")
  if any(line in block for line in forbidden):
    raise TriggerFilterError("unrequested automatic or manual trigger")
  sections = {}
  current = None
  for line in block:
    match = re.fullmatch(r"    (paths|branches-ignore):", line)
    if match:
      current = match.group(1)
      sections[current] = []
      continue
    if re.fullmatch(r"    [A-Za-z-]+:", line):
      current = None
    value = re.fullmatch(r"      - (.+)", line)
    if value and current:
      sections[current].append(value.group(1).strip("'\""))
  if set(sections) != {"paths", "branches-ignore"}:
    raise TriggerFilterError("unsupported or missing path/branch filter")
  return sections


def validate_on_demand(text):
  filters = extract_push_filters(text)
  if filters["paths"] != [".ci/run"]:
    raise TriggerFilterError("push paths must contain only .ci/run")
  exclusions = set(filters["branches-ignore"])
  required = {"main", "prelim-main", "prelim-main-*"}
  if not required.issubset(exclusions):
    raise TriggerFilterError("missing main or prelim-main branch exclusion")
  return filters


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("workflow", type=Path)
  args = parser.parse_args()
  try:
    validate_on_demand(args.workflow.read_text(encoding="utf-8"))
  except (OSError, TriggerFilterError) as error:
    parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
  main()
