#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys


def fail(message: str) -> None:
  print(message, file=sys.stderr)
  raise SystemExit(2)


def gh(repository: str, *arguments: str) -> str:
  result = subprocess.run(
    ["gh", *arguments, "--repo", repository],
    capture_output=True,
    text=True,
  )
  if result.returncode:
    detail = (result.stderr or result.stdout).strip()
    fail("GitHub repo-info operation failed" + (f": {detail}" if detail else ""))
  return result.stdout


def repository_info(repository: str) -> None:
  parts = repository.split("/")
  if len(parts) != 2 or not all(parts):
    fail("GitHub repository identity is malformed")
  print(json.dumps({
    "schema_version": 1,
    "repository": repository,
    "provider": "github",
  }, separators=(",", ":")))


def issue_get(repository: str, issue: int) -> None:
  raw = gh(
    repository,
    "issue",
    "view",
    str(issue),
    "--json",
    "number,title,state,url",
  )
  try:
    value = json.loads(raw)
    number = int(value["number"])
    title = value["title"]
    state = value["state"].lower()
    link = value["url"]
    if number <= 0 or not isinstance(title, str) or not title:
      raise ValueError("invalid issue identity")
    if state not in {"open", "closed"}:
      raise ValueError("invalid issue state")
    if not isinstance(link, str) or not link.startswith(("https://", "http://")):
      raise ValueError("invalid issue link")
  except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
    fail(f"GitHub issue response is malformed: {exc}")
  print(json.dumps({
    "schema_version": 1,
    "number": number,
    "title": title,
    "state": state,
    "link": link,
  }, separators=(",", ":")))


def issue_list_open(repository: str) -> None:
  raw = gh(
    repository,
    "issue",
    "list",
    "--state",
    "open",
    "--limit",
    "1000",
    "--json",
    "number,title",
  )
  try:
    values = json.loads(raw)
    if not isinstance(values, list):
      raise ValueError("expected issue array")
    issues = []
    for value in values:
      number = int(value["number"])
      title = value["title"]
      if number <= 0 or not isinstance(title, str) or not title:
        raise ValueError("invalid issue entry")
      issues.append({"number": number, "title": title})
    issues.sort(key=lambda item: item["number"])
    if len({item["number"] for item in issues}) != len(issues):
      raise ValueError("duplicate issue number")
  except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
    fail(f"GitHub issue-list response is malformed: {exc}")
  print(json.dumps({
    "schema_version": 1,
    "issues": issues,
  }, separators=(",", ":")))


def main(arguments: list[str]) -> int:
  parser = argparse.ArgumentParser()
  parser.add_argument("--repository", required=True)
  known, words = parser.parse_known_args(arguments)
  repository = known.repository

  if words == ["repository"]:
    repository_info(repository)
    return 0
  if words == ["issue", "list-open"]:
    issue_list_open(repository)
    return 0
  if len(words) == 3 and words[:2] == ["issue", "get"]:
    try:
      issue = int(words[2])
    except ValueError:
      fail("issue number must be a positive integer")
    if issue <= 0:
      fail("issue number must be a positive integer")
    issue_get(repository, issue)
    return 0
  fail("usage: repository | issue list-open | issue get ISSUE")
  return 2


if __name__ == "__main__":
  raise SystemExit(main(sys.argv[1:]))
