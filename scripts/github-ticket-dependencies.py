#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys


def fail(message: str) -> None:
  print(message, file=sys.stderr)
  raise SystemExit(2)


def gh(*arguments: str) -> str:
  result = subprocess.run(
    ["gh", *arguments],
    capture_output=True,
    text=True,
  )
  if result.returncode:
    detail = (result.stderr or result.stdout).strip()
    fail("GitHub dependency operation failed" + (f": {detail}" if detail else ""))
  return result.stdout


def _connection(value: dict, field: str) -> tuple[int, ...]:
  connection = value[field]
  if (
    not isinstance(connection, dict)
    or set(connection) != {"nodes", "totalCount"}
  ):
    raise ValueError(f"{field} must contain nodes and totalCount")
  nodes = connection["nodes"]
  total = connection["totalCount"]
  if not isinstance(nodes, list):
    raise ValueError(f"{field}.nodes must be an array")
  if isinstance(total, bool) or not isinstance(total, int) or total < 0:
    raise ValueError(f"{field}.totalCount must be a non-negative integer")
  if total != len(nodes):
    raise ValueError(
      f"{field} relationship set is truncated: "
      f"totalCount={total}, nodes={len(nodes)}"
    )
  numbers = []
  for item in nodes:
    if not isinstance(item, dict):
      raise ValueError(f"{field} node must be an object")
    number = item.get("number")
    if isinstance(number, bool) or not isinstance(number, int):
      raise ValueError(f"{field} node number must be an integer")
    numbers.append(number)
  normalized = tuple(sorted(set(numbers)))
  if len(normalized) != len(numbers):
    raise ValueError(f"{field} contains duplicate issue numbers")
  return normalized


def read_related(issue: int) -> tuple[tuple[int, ...], tuple[int, ...]]:
  raw = gh("issue", "view", str(issue), "--json", "blockedBy,blocking")
  try:
    value = json.loads(raw)
    blocked_by = _connection(value, "blockedBy")
    blocking = _connection(value, "blocking")
  except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
    fail(f"GitHub dependency response is malformed: {exc}")
  if any(number <= 0 for number in (*blocked_by, *blocking)):
    fail("GitHub dependency response contains an invalid issue number")
  if issue in blocked_by or issue in blocking:
    fail("GitHub dependency response contains an invalid issue number")
  return blocked_by, blocking


def read(issue: int) -> tuple[int, ...]:
  blocked_by, _ = read_related(issue)
  return blocked_by


def emit(issue: int, dependencies: tuple[int, ...]) -> None:
  print(json.dumps({
    "schema_version": 1,
    "issue": issue,
    "dependencies": list(dependencies),
  }, separators=(",", ":")))


def main(arguments: list[str]) -> int:
  if len(arguments) < 3 or arguments[:2] not in (
    ["dependency", "get"],
    ["dependency", "related"],
    ["dependency", "replace"],
  ):
    fail(
      "usage: dependency get ISSUE | dependency related ISSUE | "
      "dependency replace ISSUE [DEPENDENCY...]"
    )
  try:
    issue = int(arguments[2])
    requested = tuple(sorted({int(item) for item in arguments[3:]}))
  except ValueError:
    fail("issue numbers must be positive integers")
  if issue <= 0 or any(number <= 0 for number in requested):
    fail("issue numbers must be positive integers")
  if issue in requested:
    fail("self dependency is invalid")

  operation = arguments[1]
  if operation == "related":
    if len(arguments) != 3:
      fail("dependency related accepts exactly one issue")
    dependencies, dependants = read_related(issue)
    print(json.dumps({
      "schema_version": 1,
      "issue": issue,
      "dependencies": list(dependencies),
      "dependants": list(dependants),
    }, separators=(",", ":")))
    return 0

  current = read(issue)
  if operation == "get":
    if len(arguments) != 3:
      fail("dependency get accepts exactly one issue")
    emit(issue, current)
    return 0

  remove = tuple(number for number in current if number not in requested)
  add = tuple(number for number in requested if number not in current)
  if remove:
    gh(
      "issue", "edit", str(issue),
      "--remove-blocked-by", ",".join(str(number) for number in remove),
    )
  if add:
    gh(
      "issue", "edit", str(issue),
      "--add-blocked-by", ",".join(str(number) for number in add),
    )

  confirmed = read(issue)
  if confirmed != requested:
    fail(
      "GitHub dependency replacement could not be confirmed; "
      "reread and reconcile provider state"
    )
  emit(issue, confirmed)
  return 0


if __name__ == "__main__":
  raise SystemExit(main(sys.argv[1:]))
