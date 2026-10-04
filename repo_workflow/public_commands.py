from __future__ import annotations

from .command_grammar import Context, validate_node
from .workflow_state import derive_plan, discover_facts
from .workspace_store import WorkspaceStore


def _plan(context: Context):
  return derive_plan(discover_facts(context.root))


def _integration_results(context: Context) -> dict:
  descriptions = {
    "succeeded": "Report integration tests succeeded",
    "failed": "Report integration tests failed",
  }
  if not context.legal_only:
    names = ("failed", "succeeded")
  else:
    allowed = set(_plan(context).transitions)
    names = tuple(
      name
      for name in ("failed", "succeeded")
      if f"validate integration {name}" in allowed
    )
  return {
    "completions": [{name: descriptions[name]} for name in names],
  }


def _integration_node() -> dict:
  return {
    "_values": _integration_results,
  }


def _regression_node() -> dict:
  return {
    "": "Run all regression tests",
  }


def _validate_commands(context: Context) -> dict:
  issue_tests = {"issue": {"_values": _issue_number}}
  if not context.legal_only:
    return {
      "completions": [
        {"regression": _regression_node()},
        {"integration": _integration_node()},
        issue_tests,
      ],
    }

  transitions = _plan(context).transitions
  fragments: list[dict] = []
  if "validate regression" in transitions:
    fragments.append({"regression": _regression_node()})
  if any(item.startswith("validate integration ") for item in transitions):
    fragments.append({"integration": _integration_node()})
  fragments.append(issue_tests)
  return {"completions": fragments}


def _issue_number(context: Context) -> dict:
  token = context.current_token
  if token and token.isdecimal():
    return {"completions": [token]}
  return {"completions": []}


def _workspace_ids(context: Context) -> dict:
  try:
    values = [
      workspace["workspace_id"]
      for workspace in WorkspaceStore(context.root).list_workspaces()
    ]
  except Exception:
    values = []
  return {"completions": values}


def _workspace_value() -> dict:
  return {"_values": _workspace_ids}


def _workspace_commands() -> dict:
  return {
    "ready": "Show canonical issue readiness and blockers",
    "list": "List local workspaces",
    "create": {"_values": _issue_number},
    "info": {
      "": "Show the current workspace",
      "_values": _workspace_ids,
    },
    "claim": _workspace_value(),
    "release": _workspace_value(),
    "resume": _workspace_value(),
    "close": _workspace_value(),
  }


COMMANDS = {
  "issue": {
    "start": {
      "_values": _issue_number,
    },
  },
  "workspace": _workspace_commands(),
  "tests": {
    "sync": "Synchronize executable tests for current work",
    "view": {
      "": "View proposed executable tests",
      "new": "View proposed executable tests",
      "old": "View trusted executable tests before proposal",
    },
    "accept": {
      "new": "Accept proposed executable tests and continue start",
      "old": "Retain existing executable tests and continue start",
    },
    "_variadic": {"min": 1, "description": "Review pending tests with Git"},
  },
  "what-next": {
    "": "Show legal next workflow transitions",
    "--json": "Output workflow guidance as JSON",
  },
  "validate": {
    "_values": _validate_commands,
  },
  "version": {
    "": "Show the repository version",
    "--json": "Output the repository version as JSON",
    "task": {
      "issue": {
        "_values": _issue_number,
      },
    },
    "integrate": {
      "increment": {
        "patch": "Request a patch integration version",
        "minor": "Request a minor integration version",
      },
    },
    "release-major": "Request the next major release version",
  },
}


validate_node(COMMANDS)


PUBLIC_COMMANDS = frozenset(COMMANDS)
