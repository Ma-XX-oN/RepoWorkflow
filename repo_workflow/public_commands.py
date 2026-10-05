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
  if not context.legal_only:
    return {
      "completions": [
        {"regression": _regression_node()},
        {"integration": _integration_node()},
      ],
    }

  transitions = _plan(context).transitions
  fragments: list[dict] = []
  if "validate regression" in transitions:
    fragments.append({"regression": _regression_node()})
  if any(item.startswith("validate integration ") for item in transitions):
    fragments.append({"integration": _integration_node()})
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
  return {
    "_values": _workspace_ids,
    "_value_description": "Workspace ID",
  }


def _workspace_commands() -> dict:
  return {
    "ready": "Show canonical issue readiness and blockers",
    "list": "List local workspaces",
    "create": {
      "_values": _issue_number,
      "_value_description": "Issue number",
    },
    "info": {
      "": "Show the current workspace",
      "_values": _workspace_ids,
      "_value_description": "Workspace ID",
    },
    "claim": _workspace_value(),
    "release": _workspace_value(),
    "resume": _workspace_value(),
    "close": _workspace_value(),
  }


COMMANDS = {
  "init": {
    "": "Initialize RepoWorkflow in this repository",
    "local-only": "Initialize clone-local RepoWorkflow state",
    "bash": "Emit Bash shell initialization",
    "zsh": "Emit Zsh shell initialization",
  },
  "lanes": {
    "select": {
      "_variadic": {
        "min": 1,
        "description": "Issue roots, optionally followed by --json",
      },
      "add": {
        "_variadic": {
          "min": 1,
          "description": "Issue roots, optionally followed by --json",
        },
      },
      "remove": {
        "_variadic": {
          "min": 1,
          "description": "Issue roots, optionally followed by --json",
        },
      },
    },
    "list": {
      "": "Render local lane selection",
      "--links": "Render local lane selection with issue links",
      "_variadic": {"min": 1, "description": "Lane and optional --links"},
    },
    "clear": "Clear local lane selection",
  },
  "settings": {
    "color": {
      "auto": "Use color when output is a terminal",
      "always": "Always use color",
      "never": "Never use color",
    },
  },
  "issue": {
    "select": {
      "dependency": {
        "to-tickets": {"": "Synchronize RWF dependencies to tickets", "--compare": "Compare without mutation", "--replace": "Replace conflicting ticket dependencies"},
        "from-tickets": {"": "Synchronize ticket dependencies to RWF", "--compare": "Compare without mutation", "--replace": "Replace conflicting RWF dependencies"},
      },
    },
    "info": {
      "": "List open issues",
      "_values": _issue_number,
      "_value_description": "Issue number",
    },
    "list": {
      "": "List all open issues",
      "--links": "List all open issues with links",
      "_variadic": {
        "min": 1,
        "description": "Issue IDs, optionally followed by --links",
      },
    },
    "start": {
      "_values": _issue_number,
      "_value_description": "Issue number",
    },
  },
  "workspace": _workspace_commands(),
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
        "_value_description": "Issue number",
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
