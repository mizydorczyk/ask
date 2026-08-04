# `?` is a one-character glob in Zsh, so disable globbing before dispatching.
autoload -Uz add-zsh-hook
typeset -ga _ASK_SESSION_HISTORY=()

_ask_record_command() {
  _ASK_SESSION_HISTORY+=("$1")
  while (( ${#_ASK_SESSION_HISTORY} > 21 )); do
    _ASK_SESSION_HISTORY[1]=()
  done
}

(( ${preexec_functions[(Ie)_ask_record_command]} )) || \
  add-zsh-hook preexec _ask_record_command

ask() {
  local previous_status=$?

  case ${1-} in
    (initialize | request | -*)
      command ask "$@"
      ;;
    (*)
      _ask_request "$previous_status" "$@"
      ;;
  esac
}

alias '?'='noglob ask'

_ask_with_context() {
  local previous_status=$1
  local subcommand=$2
  shift 2

  local history_count=${#_ASK_SESSION_HISTORY}
  local current_command=${_ASK_SESSION_HISTORY[$history_count]-}
  local previous_command=""
  if (( history_count > 1 )); then
    previous_command=${_ASK_SESSION_HISTORY[$(( history_count - 1 ))]}
  fi
  local -a metadata=(
    --previous-command "$previous_command"
    --current-command "$current_command"
    --cwd "$PWD"
    --tty "$TTY"
    --previous-status "$previous_status"
    --terminal-program "${TERM_PROGRAM-}"
  )
  local history_index history_entry
  for (( history_index = 1; history_index < history_count; history_index++ )); do
    history_entry=${_ASK_SESSION_HISTORY[$history_index]}
    metadata+=(--history-entry "$history_entry")
  done

  if [[ $subcommand == request ]]; then
    command ask request "${metadata[@]}" -- "$@"
  else
    command ask "$subcommand" "${metadata[@]}"
  fi
}

_ask_request() {
  local previous_status=$1
  shift

  local response
  response=$(_ask_with_context "$previous_status" request "$@")
  local response_status=$?
  if (( response_status != 0 )); then
    return $response_status
  fi

  local action=${response%%$'\n'*}
  local command_text=""
  if [[ $response == *$'\n'* ]]; then
    command_text=${response#*$'\n'}
  fi

  case $action in
    (run)
      [[ -n $command_text ]] || return 1
      print -s -- "$command_text"
      eval -- "$command_text"
      ;;
    (edit)
      [[ -n $command_text ]] || return 1
      print -rz -- "$command_text"
      ;;
    (cancel | done)
      ;;
    (*)
      print -u2 -r -- "ask: invalid action"
      return 1
      ;;
  esac
}
