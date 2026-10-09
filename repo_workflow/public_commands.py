from __future__ import annotations

from .command_grammar import Context, validate_node
from .test_catalogue import TestCatalogueError, load_test_catalogue
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
    "_description": "Report an integration test outcome",
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


def _issue_number(context: Context) -> list[str]:
  token = context.current_token
  if token and token.isdecimal():
    return [token]
  return []


def _lane_name(context: Context) -> list[str]:
  token = context.current_token
  if token and not token.startswith("--"):
    return [token]
  return []


def _high_risk_aliases(context: Context) -> list[str]:
  try:
    return list(load_test_catalogue(context.root).alias_names())
  except TestCatalogueError:
    return []


def _lane_select_switches(*, include_count: bool = False) -> dict:
  switches = {
    "--dependencies": "Include seed and transitive dependencies",
    "--dependents": "Include seed and transitive dependents",
    "--single": "Include only the seed",
    "--refresh": "Refresh relationship and issue data",
    "--json": "Output selection as JSON",
  }
  if include_count:
    switches["--count"] = (
      "Count projected issues without graph layout or rendering"
    )
  return switches


def _dependency_direction_node() -> dict:
  return {
    "_description": "Choose metadata synchronization direction",
    "to-tickets": {
      "": "Synchronize RWF title/dependencies to tickets",
      "_switches": {
        "--compare": "Compare title/dependencies without mutation",
        "--replace": "Replace conflicting ticket dependencies",
      },
    },
    "from-tickets": {
      "": "Synchronize ticket title/dependencies to RWF",
      "_switches": {
        "--compare": "Compare title/dependencies without mutation",
        "--replace": "Replace conflicting local title/dependencies",
        "--replace-title": "Replace provider-authoritative title only",
        "--replace-dependencies": "Replace local dependencies only",
      },
    },
  }


def _issue_sync_target_node() -> dict:
  return {
    "_description": "Synchronize issue metadata with tickets",
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


def _workspace_ids(context: Context) -> list[str]:
  try:
    return [
      workspace["workspace_id"]
      for workspace in WorkspaceStore(context.root).list_workspaces()
    ]
  except Exception:
    return []


def _workspace_value() -> dict:
  return {
    "_description": "Operate on an identified workspace",
    "_values": _workspace_ids,
    "_value_description": "Workspace ID",
  }


def _workspace_commands() -> dict:
  return {
    "_description": "Manage local workspaces and their issue claims",
    "ready": "Show canonical issue readiness and blockers",
    "list": "List local workspaces",
    "create": {
      "_description": "Create a workspace for an issue",
      "_values": _issue_number,
      "_value_description": "Issue number",
    },
    "info": {
      "": "Show the current workspace",
      "_values": _workspace_ids,
      "_value_description": "Workspace ID",
      "_quantifier": "?",
    },
    "claim": _workspace_value(),
    "release": _workspace_value(),
    "resume": _workspace_value(),
    "close": _workspace_value(),
  }


# COMMANDS grammar reference
#
#   "<param>": "<help>"
#   "<param>": param_completion_fn
#
#   "--<switch>": "<help>"
#   "--<switch>": {
#     "_params": [
#       {
#         "<param0-opt0>": ...,
#         "<param0-opt1>": ...,
#         "_quantifier": "...",
#       },
#       {
#         "<param1-opt0>": ...,
#         "<param1-opt1>": ...,
#         "_quantifier": "...",
#       },
#     ],
#     "_quantifier": "...",
#   }
#
#   "<cmd>": "<help>"
#   "<cmd>": {
#     "_values": completion_fn,
#     "_value_description": "<help>",
#     "_quantifier": "...",
#   }
#   "<cmd>": {
#     "_switches": {
#       "--<switch0>": ...,
#       "--<switch1>": ...,
#     }
#   }
#   "<cmd>": {"_switches": switch_completion_fn}
#   "<cmd>": {
#     "<cmd-opt0>": ...,
#     "<cmd-opt1>": ...,
#     "_quantifier": "...",
#   }
#   "<cmd>": {
#     "_ordered": [
#       {"<cmd0-opt0>": ..., "<cmd0-opt1>": ...},
#       {"<cmd1-opt0>": ..., "<cmd1-opt1>": ...},
#     ],
#     "_quantifier": "...",
#   }
#
# - completion_fn returns only a list of completion item strings.
# - switch_completion_fn returns a dict of valid switches for the current context.
# - param_completion_fn returns a dict of valid params for the current context.
# - "_quantifier" is optional and defaults to "{1}" for the construct beside it.
# - A switch declaration is optional by being under "_switches"; with no
#   switch-level quantifier it may occur at most once.
# - A quantifier inside a "_params" position controls that parameter position.
# - A quantifier beside "_params" controls occurrences of that switch.
# - A quantifier beside "_ordered" controls repetitions of that full sequence.
# - A quantifier beside terminal command alternatives controls an unordered
#   choice group; repeated multi-token structures use "_ordered".
# - Quantifier notation is regex-style: ?, *, +, {n}, {n,}, {n,m}.

COMMANDS = {
  "init": {
    "": "Initialize RepoWorkflow in this repository",
    "local-only": "Initialize clone-local RepoWorkflow state",
    "bash": "Emit Bash shell initialization",
    "zsh": "Emit Zsh shell initialization",
  },
  "lanes": {
    "_description": "Select, list, and render issue lanes",
    "select": {
      "_description": "Select issue focus roots",
      "": "Select issue focus roots",
      "_values": _issue_number,
      "_value_description": "Issue number",
      "_quantifier": "+",
      "_switches": _lane_select_switches(include_count=True),
      "add": {
        "_description": "Add issue focus roots",
        "": "Add issue focus roots",
        "_values": _issue_number,
        "_value_description": "Issue number",
        "_quantifier": "+",
        "_switches": _lane_select_switches(),
      },
      "remove": {
        "_description": "Remove issue focus roots",
        "": "Remove issue focus roots",
        "_values": _issue_number,
        "_value_description": "Issue number",
        "_quantifier": "+",
        "_switches": _lane_select_switches(),
      },
      "exclude": {
        "_description": "Exclude projected issues from the selection",
        "": "Exclude projected issues from the selection",
        "_values": _issue_number,
        "_value_description": "Issue number",
        "_quantifier": "+",
        "_switches": _lane_select_switches(),
      },
    },
    "list": {
      "": "List selected issues grouped by lane",
      "_values": _lane_name,
      "_value_description": "Lane",
      "_quantifier": "?",
      "_switches": {
        "--links": "Include issue links",
        "--refresh": "Refresh selected lane data before listing",
      },
    },
    "view": {
      "": "Render selected dependency topology",
      "_values": _lane_name,
      "_value_description": "Lane",
      "_quantifier": "?",
      "_switches": {
        "--refresh": "Refresh selected lane data before rendering",
        "--debug": "Show lane data sources, timings, and semantic edges",
      },
    },
    "clear": "Clear local lane selection",
  },
  "settings": {
    "_description": "Configure RepoWorkflow display settings",
    "color": {
      "_description": "Choose when to colour terminal output",
      "auto": "Use color when output is a terminal",
      "always": "Always use color",
      "never": "Never use color",
    },
  },
  "issue": {
    "_description": "Inspect, start, and synchronize issues",
    "_values": _issue_sync_target,
    "_value_description": "Issue number for dependency synchronization",
    "info": {
      "": "List open issues",
      "_values": _issue_number,
      "_value_description": "Issue number",
      "_quantifier": "?",
    },
    "list": {
      "": "List all open issues",
      "_values": _issue_number,
      "_value_description": "Issue number",
      "_quantifier": "*",
      "_switches": {
        "--links": "List issues with links",
      },
    },
    "start": {
      "_description": "Start work on an issue",
      "_values": _issue_number,
      "_value_description": "Issue number",
    },
  },
  "workspace": _workspace_commands(),
  "high-risk": {
    "_description": "Associate high-risk test sections with an issue",
    "_values": _high_risk_aliases,
    "_value_description": "Test-catalogue alias section",
    "_quantifier": "+",
  },
  "what-next": {
    "": "Show legal next workflow transitions",
    "_switches": {
      "--json": "Output workflow guidance as JSON",
    },
  },
  "validate": {
    "_description": "Run or record validation stages",
    "_values": _validate_commands,
  },
  "version": {
    "": "Show the repository version",
    "_switches": {
      "--json": "Output the repository version as JSON",
    },
    "task": {
      "_description": "Manage task-specific version transitions",
      "issue": {
        "_description": "Set the development version for an issue",
        "_values": _issue_number,
        "_value_description": "Issue number",
      },
    },
    "integrate": {
      "_description": "Select the stable integration version increment",
      "increment": {
        "_description": "Select patch or minor integration increment",
        "patch": "Request a patch integration version",
        "minor": "Request a minor integration version",
      },
    },
    "release-major": "Request the next major release version",
  },
}


validate_node(COMMANDS)


PUBLIC_COMMANDS = frozenset(COMMANDS)
