"""Public manual-integration CLI adapter; B owns durable state and evidence."""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys

from .git import current_branch, head_sha
from .test_results_reader import TestCommandError


def _issue(root: Path) -> int:
  match = re.fullmatch(r"issue-([1-9][0-9]*)(?:-.*)?", current_branch(root))
  if match is None:
    raise TestCommandError("manual integration requires a current issue branch")
  return int(match.group(1))


def _catalogue(root: Path, issue: int):
  try:
    from .manual_test_catalogue import read_manual_cases
    return read_manual_cases(root, issue)
  except ImportError as error:
    raise TestCommandError(
      "manual integration catalogue is not installed"
    ) from error
  except ValueError as error:
    raise TestCommandError(str(error)) from error


def _result_api():
  try:
    from . import manual_test_result
  except ImportError as error:
    raise TestCommandError(
      "manual integration result/state service is not installed"
    ) from error
  for name in (
    "read_active_manual_selection", "select_manual_case",
    "read_manual_case_results", "record_manual_result",
  ):
    if not callable(getattr(manual_test_result, name, None)):
      raise TestCommandError(
        "manual integration result/state service lacks " + name
      )
  return manual_test_result


def _name(selection):
  if isinstance(selection, dict):
    return selection.get("name")
  return getattr(selection, "name", None)


def _digest(selection):
  if isinstance(selection, dict):
    return selection.get("definition_digest")
  return getattr(selection, "definition_digest", None)


def _selected(api, root: Path, issue: int, sha: str, cases):
  selected = api.read_active_manual_selection(root, issue, sha)
  if isinstance(selected, (list, tuple, set)):
    raise TestCommandError("multiple active manual test selections")
  if selected is None:
    raise TestCommandError(
      "exactly one active manual test selection is required"
    )
  by_name = {case.name: case for case in cases}
  case = by_name.get(_name(selected))
  if case is None or _digest(selected) != case.definition_digest:
    raise TestCommandError(
      "manual test selection is stale or does not match current definition"
    )
  return case


def manual_case_completions(context) -> list:
  try:
    issue = _issue(context.root)
    cases = _catalogue(context.root, issue)
  except (TestCommandError, ValueError):
    return []
  return [
    {case.name: "Select manual integration test " + case.name}
    for case in cases
  ]


def manual_result_completions(context) -> list:
  if not context.legal_only:
    return [
      {"succeeded": "Record PASS for the actively selected manual test"},
      {"failed": "Record FAIL for the actively selected manual test"},
    ]
  try:
    root = context.root
    issue = _issue(root)
    cases = _catalogue(root, issue)
    _selected(_result_api(), root, issue, head_sha(root), cases)
  except (TestCommandError, ValueError, OSError):
    return []
  return [
    {"succeeded": "Record PASS for the selected manual test"},
    {"failed": "Record FAIL and block integration progression"},
  ]


def _results(api, root: Path, issue: int, sha: str, cases):
  values = api.read_manual_case_results(root, issue, sha)
  if not isinstance(values, dict):
    raise TestCommandError("manual result readback must be a name/result map")
  names = {case.name for case in cases}
  if not set(values).issubset(names):
    raise TestCommandError("manual result readback contains unknown test names")
  for name, result in values.items():
    if result not in {"succeeded", "failed", "timeout"}:
      raise TestCommandError(
        "manual result readback contains invalid result for " + name
      )
  return values


def _outstanding(root: Path):
  issue = _issue(root)
  sha = head_sha(root)
  cases = _catalogue(root, issue)
  if not cases:
    return issue, sha, cases, {}, None
  api = _result_api()
  values = _results(api, root, issue, sha, cases)
  return issue, sha, cases, values, api


def select_requested(root: Path, *, name: str | None, remote: bool) -> int:
  if remote:
    raise TestCommandError("manual integration cannot use --remote")
  issue, sha, cases, results, api = _outstanding(root)
  if not cases:
    if name is not None:
      raise TestCommandError("requested manual test is not declared")
    print("No manual tests required for this issue.")
    return 0
  if "failed" in results.values():
    raise TestCommandError(
      "a failed manual integration test blocks this candidate; repair required"
    )
  if name is None:
    case = next(
      (case for case in cases if results.get(case.name) != "succeeded"),
      None,
    )
    if case is None:
      print("No outstanding manual integration tests.")
      return 0
  else:
    case = next((item for item in cases if item.name == name), None)
    if case is None:
      raise TestCommandError("requested manual test is not declared")
    if case.name in results:
      raise TestCommandError(
        "manual test already has a terminal result: " + case.name
      )
  assert api is not None
  api.select_manual_case(root, issue, sha, case)
  observed = _selected(api, root, issue, sha, cases)
  if observed.name != case.name:
    raise TestCommandError("selected manual test did not persist correctly")
  print("Manual integration test: " + case.name)
  print("Candidate SHA: " + sha)
  print("Instructions: " + case.instructions)
  print("Expected result: " + case.expected_result)
  print("Record outcome using: rwf test succeeded | rwf test failed")
  return 0


def record_selected(root: Path, *, outcome: str) -> int:
  if outcome not in {"succeeded", "failed"}:
    raise AssertionError("unsupported manual result")
  issue = _issue(root)
  sha = head_sha(root)
  cases = _catalogue(root, issue)
  api = _result_api()
  case = _selected(api, root, issue, sha, cases)
  current = _results(api, root, issue, sha, cases)
  if case.name in current:
    raise TestCommandError(
      "manual test already has a terminal result: " + case.name
    )
  evidence = api.record_manual_result(root, issue, sha, outcome)
  if evidence is None:
    raise TestCommandError(
      "manual result service did not confirm durable readback"
    )
  verified = _results(api, root, issue, sha, cases)
  if verified.get(case.name) != outcome:
    raise TestCommandError(
      "manual result readback mismatch; outcome is not accepted"
    )
  print("Manual integration " + outcome.upper() + ": " + case.name)
  if isinstance(evidence, dict):
    print(json.dumps(evidence, sort_keys=True))
  return 1 if outcome == "failed" else 0


def after_automatic_integration(root: Path) -> int:
  catalogue = root / ".ci" / "tests.json"
  if not catalogue.is_file():
    return 0
  # Keep existing AIT behaviour for catalogues without manual cases.
  # Never silently succeed if manual entries exist and A/B are unavailable.
  if "manual--" not in catalogue.read_text(encoding="utf-8"):
    return 0
  issue, sha, cases, results, _ = _outstanding(root)
  if not cases:
    print("No manual tests required for this issue.")
    return 0
  outstanding = [case.name for case in cases
                 if results.get(case.name) != "succeeded"]
  if not outstanding:
    print("All manual integration tests have passed for " + sha)
    return 0
  print(
    "Manual integration incomplete: "
    + str(len(outstanding)) + " outstanding test(s).",
    file=sys.stderr,
  )
  for name in outstanding:
    print("  " + name, file=sys.stderr)
  print("Run: rwf test integration --manual", file=sys.stderr)
  return 2
