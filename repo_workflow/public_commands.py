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


def _dependency_direction_node() -> dict:
  return {
    "to-tickets": {
      "": "Synchronize RWF title/dependencies to tickets",
      "--compare": "Compare title/dependencies without mutation",
      "--replace": "Replace conflicting ticket dependencies",
    },
    "from-tickets": {
      "": "Synchronize ticket title/dependencies to RWF",
      "--compare": "Compare title/dependencies without mutation",
      "--replace": "Replace conflicting local title/dependencies",
      "--replace-title": "Replace provider-authoritative title only",
      "--replace-dependencies": "Replace local dependencies only",
    },
  }


def _issue_sync_target_node() -> dict:
  return {
    "dependency": _dependency_direction_node(),
    "_values": _issue_sync_target,
    "_value_description": "Additional issue number",
  }


def _issue_sync_target(context: Context) -> dict:
  token = context.current_token
  if token and token.isdecimal() and int(token) > 0:
    return {
      "completions": [
        {token: _issue_sync_target_node()},
      ],
    }
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


# COMMANDS grammar reference
#
#   "<cmd>": "<help>"
#   "--<switch>": "<help>"
#   "<param>": "<help>"
#   "<param>": param_completion_fn
#   "--<switch>": [
#     {
#       "<param0-opt-0>": ...,
#       "<param0-opt-1>": ...,
#       ...,
#       "_quantifier": "...",
#     },
#     {
#       "<param1-opt-0>": ...,
#       "<param1-opt-1>": ...,
#       ...,
#       "_quantifier": "...",
#     },
#     ...
#   ]
#   "<cmd>": {
#     "_values": completion_fn,
#     "_value_description": "<help>",
#     "_quantifier": "...",
#   }
#   "<cmd>": {
#     "_switches": {
#       "--<switch0>": ...,
#       "--<switch1>": ...,
#       ...
#     }
#   }
#   "<cmd>": {"_switches": switch_completion_fn}
#   "<cmd>": {
#     "<cmd0>": ...,
#     "<cmd1>": ...,
#     ...,
#     "_quantifier": "...",
#   }
#
# completion_fn returns only a list of completion item strings.
# switch_completion_fn returns a dict of valid switches for the current context.
# param_completion_fn returns a dict of valid params for the current context.
# "_quantifier" is optional and defaults to "{1}".
# There is no "_variadic" grammar item in the quantified grammar.


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
        "description": "Issue focus seeds, optionally followed by --refresh/--json",
      },
      "add": {
        "_variadic": {
          "min": 1,
          "description": "Issue focus seeds, optionally followed by --refresh/--json",
        },
      },
      "remove": {
        "_variadic": {
          "min": 1,
          "description": "Issue focus seeds, optionally followed by --refresh/--json",
        },
      },
    },
    "list": {
      "": "List selected issues grouped by lane",
      "--links": {
        "": "List selected issues with links",
        "--refresh": "Refresh selected lane data and include links",
      },
      "--refresh": {
        "": "Refresh selected lane data before listing",
        "--links": "Refresh selected lane data and include links",
      },
      "_variadic": {
        "min": 1,
        "description": "Lane and optional --links/--refresh",
      },
    },
    "view": {
      "": "Render selected dependency topology",
      "--refresh": {
        "": "Refresh selected lane data before rendering",
        "--debug": "Refresh and show lane diagnostics",
      },
      "--debug": {
        "": "Show lane data sources, timings, and semantic edges",
        "--refresh": "Refresh and show lane diagnostics",
      },
      "_variadic": {
        "min": 1,
        "description": "Lane and optional --refresh/--debug",
      },
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
    "_values": _issue_sync_target,
    "_value_description": "Issue number for dependency synchronization",
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
