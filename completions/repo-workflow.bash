# Bash completion for repo-workflow / rwf.
# Suggestions come from RepoWorkflow's state machine through the hidden
# `complete` projection command; this file contains no workflow policy.

_repo_workflow_complete() {
  local command="${REPO_WORKFLOW_COMMAND:-repo-workflow}"
  local root="${REPO_WORKFLOW_ROOT:-$PWD}"
  local -a words=("${COMP_WORDS[@]:1}")
  COMPREPLY=()
  mapfile -t COMPREPLY < <(
    "$command" --root "$root" complete "${words[@]}" 2>/dev/null
  )
}

complete -F _repo_workflow_complete repo-workflow rwf
