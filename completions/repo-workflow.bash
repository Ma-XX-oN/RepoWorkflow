# RepoWorkflow managed Bash integration v1
# Both command names resolve the current Git worktree and delegate to that
# repository's own stable RepoWorkflow launcher. Completion is a projection of
# the same state machine; this file contains no workflow policy.

_rwf_worktree_root() {
  command git rev-parse --show-toplevel 2>/dev/null
}

_rwf_python() {
  if [[ -n "${PYTHON:-}" ]]; then
    printf '%s\n' "$PYTHON"
    return 0
  fi
  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return 0
  fi
  if command -v python >/dev/null 2>&1; then
    command -v python
    return 0
  fi
  printf '%s\n' 'RepoWorkflow error: Python interpreter not found' >&2
  return 2
}

_rwf_invoke() {
  local root
  root="$(_rwf_worktree_root)" || {
    printf '%s\n' 'RepoWorkflow error: not inside a Git worktree' >&2
    return 2
  }

  if [[ ! -f "$root/.ci/repoworkflow.json" ]]; then
    printf 'RepoWorkflow error: Git worktree is not a RepoWorkflow consumer: %s\n' "$root" >&2
    return 2
  fi

  local python
  python="$(_rwf_python)" || return $?

  if [[ -f "$root/scripts/repoworkflow.py" ]]; then
    "$python" "$root/scripts/repoworkflow.py" --root "$root" "$@"
    return $?
  fi
  if [[ -x "$root/RepoWorkflow/repo-workflow" ]]; then
    "$root/RepoWorkflow/repo-workflow" --root "$root" "$@"
    return $?
  fi
  if [[ -f "$root/RepoWorkflow/repo_workflow.py" ]]; then
    "$python" "$root/RepoWorkflow/repo_workflow.py" --root "$root" "$@"
    return $?
  fi
  if [[ -x "$root/repo-workflow" ]]; then
    "$root/repo-workflow" --root "$root" "$@"
    return $?
  fi
  if [[ -f "$root/repo_workflow.py" ]]; then
    "$python" "$root/repo_workflow.py" --root "$root" "$@"
    return $?
  fi

  printf 'RepoWorkflow error: no repository-local RepoWorkflow launcher found in %s\n' "$root" >&2
  return 2
}

rwf() {
  _rwf_invoke "$@"
}

repo-workflow() {
  _rwf_invoke "$@"
}

_repo_workflow_complete() {
  local -a words=("${COMP_WORDS[@]:1:$COMP_CWORD}")
  COMPREPLY=()
  mapfile -t COMPREPLY < <(
    _rwf_invoke complete -- "${words[@]}" 2>/dev/null
  )
}

complete -F _repo_workflow_complete repo-workflow rwf
