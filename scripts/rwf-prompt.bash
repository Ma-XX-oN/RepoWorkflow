# Source this file, supplying the absolute path to repo_workflow.py as argument 1.
# Example: source scripts/rwf-prompt.bash "$PWD/repo_workflow.py"
if [[ -z ${1-} ]]; then
  printf '%s\n' 'rwf-prompt: supply the absolute repo_workflow.py path' >&2
  return 2
fi
RWF_PROMPT_ENGINE=$1
_rwf_manual_prompt() {
  local rwf_status=$? rwf_prefix rwf_python
  if [[ -n ${RWF_PROMPT_PREFIX-} && $PS1 == "$RWF_PROMPT_PREFIX"* ]]; then
    PS1=${PS1#"$RWF_PROMPT_PREFIX"}
  fi
  rwf_prefix=
  for rwf_python in python3 python; do
    if "$rwf_python" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then
      rwf_prefix=$("$rwf_python" "$RWF_PROMPT_ENGINE" --root "$PWD" manual-prompt 2>/dev/null) || rwf_prefix=
      break
    fi
  done
  RWF_PROMPT_PREFIX=
  if [[ $rwf_prefix =~ ^\[MIT\ [0-9]+/[0-9]+\]$ ]]; then
    RWF_PROMPT_PREFIX="$rwf_prefix "
    PS1="$RWF_PROMPT_PREFIX$PS1"
  fi
  return "$rwf_status"
}
if [[ $(declare -p PROMPT_COMMAND 2>/dev/null) == 'declare -a '* ]]; then
  if [[ " ${PROMPT_COMMAND[*]} " != *' _rwf_manual_prompt '* ]]; then
    PROMPT_COMMAND+=(_rwf_manual_prompt)
  fi
elif [[ ${PROMPT_COMMAND-} != *'_rwf_manual_prompt'* ]]; then
  PROMPT_COMMAND="${PROMPT_COMMAND:+$PROMPT_COMMAND; }_rwf_manual_prompt"
fi
