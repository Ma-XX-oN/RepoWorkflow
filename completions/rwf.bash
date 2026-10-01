# Bash completion for RepoWorkflow.
# Candidate policy is computed by `repo-workflow complete`, which projects the
# same state-machine result used by `repo-workflow what-next`.

_rwf_complete() {
  local command="${RWF_COMPLETION_COMMAND:-${COMP_WORDS[0]}}"
  local -a words
  local output

  words=("${COMP_WORDS[@]:1:$COMP_CWORD}")
  if ! output="$("$command" complete -- "${words[@]}" 2>/dev/null)"; then
    COMPREPLY=()
    return 0
  fi

  COMPREPLY=()
  if [[ -n "$output" ]]; then
    mapfile -t COMPREPLY <<< "$output"
  fi
}

complete -F _rwf_complete repo-workflow rwf
