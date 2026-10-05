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


def read(issue: int) -> tuple[int, ...]:
  raw = gh("issue", "view", str(issue), "--json", "blockedBy")
  try:
    value = json.loads(raw)
    blocked = value["blockedBy"]
    numbers = tuple(sorted({int(item["number"]) for item in blocked}))
  except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
    fail(f"GitHub dependency response is malformed: {exc}")
  if any(number <= 0 for number in numbers) or issue in numbers:
    fail("GitHub dependency response contains an invalid issue number")
  return numbers


def emit(issue: int, dependencies: tuple[int, ...]) -> None:
  print(json.dumps({
    "schema_version": 1,
    "issue": issue,
    "dependencies": list(dependencies),
  }, separators=(",", ":")))


def main(arguments: list[str]) -> int:
  if len(arguments) < 3 or arguments[:2] not in (
    ["dependency", "get"],
    ["dependency", "replace"],
  ):
    fail("usage: dependency get ISSUE | dependency replace ISSUE [DEPENDENCY...]")
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
