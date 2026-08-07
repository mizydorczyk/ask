# `?` is a one-character glob in Zsh, so disable globbing before dispatching.
autoload -Uz add-zsh-hook
typeset -ga _ASK_SESSION_HISTORY=()
typeset -ga _ASK_EVENTS=()
typeset -g _ASK_PENDING_REQUEST=""
typeset -g _ASK_PENDING_STATUS=0
typeset -g _ASK_EDIT_COMMAND=""
typeset -g _ASK_EDIT_REVIEW_COMMAND=""
typeset -g _ASK_EDIT_CWD=""
typeset -g _ASK_EDIT_ACTIVE=0

_ask_append_execution() {
  local command_text=$1 cwd_before=$2 exit_code=$3 review_command=${4:-$1} event
  event=$(command ask event --command "$command_text" --cwd-before "$cwd_before" \
    --cwd-after "$PWD" --exit-status "$exit_code" --tty "$TTY" \
    --review-command "$review_command") || return
  _ASK_EVENTS+=("$event")
}

_ask_record_edited_execution() {
  [[ -n $_ASK_EDIT_COMMAND && $_ASK_EDIT_ACTIVE -eq 1 ]] || return
  _ask_append_execution "$_ASK_EDIT_COMMAND" "$_ASK_EDIT_CWD" "$?" \
    "$_ASK_EDIT_REVIEW_COMMAND"
  _ASK_EDIT_COMMAND=""
  _ASK_EDIT_REVIEW_COMMAND=""
  _ASK_EDIT_CWD=""
  _ASK_EDIT_ACTIVE=0
}

_ask_record_command() {
  _ASK_SESSION_HISTORY+=("$1")
  if [[ -n $_ASK_EDIT_COMMAND && $_ASK_EDIT_ACTIVE -eq 0 ]]; then
    _ASK_EDIT_COMMAND=$1
    _ASK_EDIT_CWD=$PWD
    _ASK_EDIT_ACTIVE=1
  fi
  while (( ${#_ASK_SESSION_HISTORY} > 21 )); do
    _ASK_SESSION_HISTORY[1]=()
  done
}

(( ${preexec_functions[(Ie)_ask_record_command]} )) || \
  add-zsh-hook preexec _ask_record_command
(( ${precmd_functions[(Ie)_ask_record_edited_execution]} )) || \
  add-zsh-hook precmd _ask_record_edited_execution

_ask_dispatch_pending() {
  [[ -n $_ASK_PENDING_REQUEST ]] || return

  local request=$_ASK_PENDING_REQUEST
  local previous_status=$_ASK_PENDING_STATUS
  _ASK_PENDING_REQUEST=""
  print -s -- "? $request"
  _ask_record_command "? $request"
  _ask_request "$previous_status" "$request"
}

(( ${precmd_functions[(Ie)_ask_dispatch_pending]} )) || \
  add-zsh-hook precmd _ask_dispatch_pending

ask() {
  local previous_status=$?

  case ${1-} in
    (request | -*)
      command ask "$@"
      ;;
    (snapshot)
      _ask_snapshot "$previous_status" "${@:2}"
      ;;
    (*)
      _ask_request "$previous_status" "$@"
      ;;
  esac
}

alias '?'='noglob ask'

# Clean up the raw-input keymap used by earlier versions. Shell startup files
# are commonly re-sourced, so removing the old binding here prevents a stale
# widget from taking over `?` before the normal line editor can insert it.
if (( $+widgets[_ask_start] )); then
  bindkey -M emacs '?' self-insert
  bindkey -M viins '?' self-insert
  zle -D _ask_start
fi
if (( $+widgets[_ask_submit] )); then
  zle -D _ask_submit
fi

# A question can contain shell syntax (notably apostrophes). Capture it before
# the shell parser sees it, then dispatch it from precmd after ZLE exits. This
# preserves the exact line the user typed and keeps terminal output/review UI
# outside the line editor.
_ask_accept_line() {
  if [[ $BUFFER == \?* && $BUFFER != "?" ]]; then
    local previous_status=$?
    local request=${BUFFER#\?}
    request=${request# }
    if [[ -n $request ]]; then
      _ASK_PENDING_REQUEST=$request
      _ASK_PENDING_STATUS=$previous_status
      zle .send-break
      return
    fi
  fi

  if (( $+functions[_ask_original_accept_line] )); then
    zle _ask_original_accept_line -- "$@"
  else
    zle .accept-line
  fi
}

# Wrap the current accept-line widget instead of replacing its key bindings.
# Plugins such as zsh-autosuggestions wrap this widget themselves; saving and
# calling the current version keeps their Enter-key behavior intact.
if (( ! $+functions[_ask_original_accept_line] )); then
  case $widgets[accept-line] in
    (user:*) zle -N _ask_original_accept_line "${widgets[accept-line]#user:}"
      ;;
    (*) ;;
  esac
fi
zle -N accept-line _ask_accept_line

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
  local event
  for event in "${_ASK_EVENTS[@]}"; do
    metadata+=(--event "$event")
  done
  local history_index history_entry
  for (( history_index = 1; history_index < history_count; history_index++ )); do
    history_entry=${_ASK_SESSION_HISTORY[$history_index]}
    metadata+=(--history-entry "$history_entry")
  done

  if [[ $subcommand == request ]]; then
    command ask request "${metadata[@]}" -- "$@"
  elif [[ $subcommand == snapshot ]]; then
    command ask snapshot "${metadata[@]}" "$@"
  else
    command ask "$subcommand" "${metadata[@]}"
  fi
}

_ask_snapshot() {
  local previous_status=$1
  shift

  _ask_with_context "$previous_status" snapshot "$@"
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
  response=${response#*$'\n'}
  local event_update=${response%%$'\n'*}
  local command_text=""
  if [[ $response == *$'\n'* ]]; then
    command_text=${response#*$'\n'}
  fi
  [[ -n $event_update ]] && _ASK_EVENTS+=("$event_update")

  case $action in
    (run)
      [[ -n $command_text ]] || return 1
      print -s -- "$command_text"
      local cwd_before=$PWD
      eval -- "$command_text"
      local command_status=$?
      _ask_append_execution "$command_text" "$cwd_before" "$command_status"
      return $command_status
      ;;
    (edit)
      [[ -n $command_text ]] || return 1
      _ASK_EDIT_COMMAND=$command_text
      _ASK_EDIT_REVIEW_COMMAND=$command_text
      _ASK_EDIT_CWD=$PWD
      _ASK_EDIT_ACTIVE=0
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
