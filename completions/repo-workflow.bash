# Bash completion for repo-workflow / rwf.
# Command and state policy live in RepoWorkflow's Python command grammar.

_RWF_LAST_CONTEXT=""
_RWF_LAST_US=0

_rwf_now_us() {
  local raw="${EPOCHREALTIME:-${SECONDS}.000000}"
  local seconds="${raw%.*}"
  local fraction="${raw#*.}000000"
  fraction="${fraction:0:6}"
  printf '%d\n' "$((10#${seconds} * 1000000 + 10#${fraction}))"
}

_repo_workflow_complete() {
  local command="${REPO_WORKFLOW_COMMAND:-repo-workflow}"
  local root="${REPO_WORKFLOW_ROOT:-$PWD}"
  local -a words=("${COMP_WORDS[@]:1:$COMP_CWORD}")
  local context="${COMP_CWORD}|${COMP_WORDS[*]}|${COMP_LINE-}|${COMP_POINT-}"
  local now_us
  local describe=0
  local output=""

  now_us="$(_rwf_now_us)"
  if [[ "$context" == "$_RWF_LAST_CONTEXT" ]] &&
     (( now_us >= _RWF_LAST_US && now_us - _RWF_LAST_US <= 1000000 )); then
    describe=1
  fi
  _RWF_LAST_CONTEXT="$context"
  _RWF_LAST_US="$now_us"
  COMPREPLY=()

  if (( describe )); then
    if output=$(
      "$command" --root "$root" complete --describe -- "${words[@]}"
    ); then
      if [[ -n "$output" ]]; then
        printf '%s\n' "$output"
      fi
    fi
    return 0
  fi

  if ! output=$("$command" --root "$root" complete -- "${words[@]}"); then
    return 0
  fi

  while IFS= read -r candidate; do
    [[ -z "$candidate" ]] && continue
    if [[ "$candidate" == "<last-terminal>" ]]; then
      printf '%s\n' "$candidate"
    else
      COMPREPLY+=("$candidate")
    fi
  done <<< "$output"
}

complete -F _repo_workflow_complete repo-workflow rwf
