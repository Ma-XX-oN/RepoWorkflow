# Source this file with the absolute repo_workflow.py path as argument 1.
if [[ -z ${1-} ]]; then
  print -u2 'rwf-prompt: supply the absolute repo_workflow.py path'
  return 2
fi
RWF_PROMPT_ENGINE=$1
_rwf_manual_prompt() {
  local rwf_status=$? rwf_prefix rwf_python
  if [[ -n ${RWF_PROMPT_PREFIX-} && $PROMPT == "$RWF_PROMPT_PREFIX"* ]]; then
    PROMPT=${PROMPT#"$RWF_PROMPT_PREFIX"}
  fi
  rwf_prefix=
  for rwf_python in python3 python; do
    if "$rwf_python" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then
      rwf_prefix=$("$rwf_python" "$RWF_PROMPT_ENGINE" --root "$PWD" manual-prompt 2>/dev/null) || rwf_prefix=
      break
    fi
  done
  RWF_PROMPT_PREFIX=
  if [[ $rwf_prefix =~ '^\[MIT [0-9]+/[0-9]+\]$' ]]; then
    RWF_PROMPT_PREFIX="$rwf_prefix "
    PROMPT="$RWF_PROMPT_PREFIX$PROMPT"
  fi
  return $rwf_status
}
autoload -Uz add-zsh-hook
add-zsh-hook -d precmd _rwf_manual_prompt
add-zsh-hook precmd _rwf_manual_prompt
