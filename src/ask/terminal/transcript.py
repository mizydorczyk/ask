import os
import subprocess
from dataclasses import dataclass

from ask.conversation import Conversation
from ask.errors import AskError

REVIEW_PREFIX = "> "
REVIEW_CONTROLS = "enter run  tab edit  esc cancel"


@dataclass(frozen=True)
class Session:
    previous_command: str
    current_command: str
    cwd: str
    tty: str
    exit_status: int
    history: list[str]
    events: list[dict] | None = None


def capture() -> str:
    """Return the complete scrollback for the tmux pane running this shell."""
    pane = os.environ.get("TMUX_PANE")
    if not pane:
        raise AskError("ask must run inside a tmux pane")

    try:
        result = subprocess.run(
            ["tmux", "capture-pane", "-p", "-J", "-S", "-", "-t", pane],
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as error:
        raise AskError("tmux is required; install tmux and start a tmux session") from error

    if result.returncode:
        detail = result.stderr.decode(errors="replace").strip()
        raise AskError(f"tmux capture failed: {detail or 'no error details'}")

    return result.stdout.decode(errors="replace")


def entries(session: Session, text: str) -> list[tuple[str, str, int | None]]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    current = session.current_command.rstrip(" \t")
    current_at = text.rfind(current)

    if current_at < 0:
        raise AskError("cannot find the current request in tmux scrollback")

    line_start = text.rfind("\n", 0, current_at) + 1
    prompt = text[line_start:current_at]
    if not prompt:
        raise AskError("cannot identify the current tmux prompt")
    prompt_suffix = prompt[-2:]

    boundary = line_start
    found: list[tuple[str, str, int | None]] = []
    latest = True

    for command in reversed(session.history):
        anchor = command.rstrip(" \t")
        candidate = text.rfind(anchor, 0, boundary)

        while candidate >= 0:
            at_line = text.rfind("\n", 0, candidate) + 1
            prefix = text[at_line:candidate]
            reviewed = prefix == REVIEW_PREFIX and text[
                candidate + len(anchor) :
            ].startswith("\n" + REVIEW_CONTROLS)

            if prefix == prompt or prefix.endswith(prompt_suffix) or reviewed:
                output_start = text.find("\n", candidate + len(anchor), boundary)
                output_start = boundary if output_start < 0 else output_start + 1

                if reviewed:
                    output_start = text.find(
                        "\n", output_start + len(REVIEW_CONTROLS), boundary
                    )
                    output_start = boundary if output_start < 0 else output_start + 1

                found.append(
                    (
                        command,
                        text[output_start:boundary].rstrip("\n"),
                        session.exit_status if latest else None,
                    )
                )
                latest = False
                boundary = at_line
                break

            candidate = text.rfind(anchor, 0, candidate)

    found.reverse()

    return [
        (command, output, status)
        for command, output, status in found
        if command.rstrip(" \t") not in {current, "clear"}
    ]


def reviewed_proposal(output: str) -> tuple[str, str, str] | None:
    controls = output.find(REVIEW_CONTROLS)
    if controls < 0 or output.rfind("\n", 0, controls) + 1 != controls:
        return None

    proposal = output.rfind("\n" + REVIEW_PREFIX, 0, controls)
    proposal = 0 if proposal < 0 and output.startswith(REVIEW_PREFIX) else proposal + 1
    if proposal < 0:
        return None

    command_start = proposal + len(REVIEW_PREFIX)
    command = output[command_start:controls].removesuffix("\n")

    terminal_output = output[controls + len(REVIEW_CONTROLS) :].removeprefix("\n")
    return output[:proposal].rstrip("\n"), command, terminal_output


def output_after_review(command: str) -> str:
    """Return output rendered after the latest review of *command*.

    Capture is best-effort: event recording must not interfere with the live
    shell command when tmux scrollback is unavailable.
    """
    text = capture().replace("\r\n", "\n").replace("\r", "\n")
    marker = f"{REVIEW_PREFIX}{command}\n{REVIEW_CONTROLS}"
    position = text.rfind(marker)
    if position < 0:
        raise AskError("cannot find the reviewed command in tmux scrollback")
    return text[position + len(marker) :].removeprefix("\n").rstrip("\n")


def conversation(session: Session, request: str, text: str) -> Conversation:
    result = Conversation()
    history = entries(session, text)
    index = 0

    while index < len(history):
        sequence = index + 1
        command, output, status = history[index]
        if command.startswith("?"):
            if output.lstrip().startswith("ask: "):
                index += 1
                continue

            result.user(command[1:].lstrip())

            reviewed = reviewed_proposal(output)
            if reviewed:
                comment, reviewed_command, reviewed_output = reviewed
                call_id = f"call_ask_shell_{sequence}"
                executed_command = (
                    reviewed_command
                    if (
                        bool(reviewed_output)
                        or reviewed_command.rstrip(" \t")
                        == session.previous_command.rstrip(" \t")
                    )
                    else None
                )
                executed_output = reviewed_output
                executed_status = status

                if (
                    executed_command is None
                    and index + 1 < len(history)
                    and not history[index + 1][0].startswith("?")
                ):
                    executed_command, executed_output, executed_status = history[
                        index + 1
                    ]
                    index += 1

                result.assistant(comment)
                result.shell_call(call_id, reviewed_command)
                if executed_command:
                    result.tool_result(
                        call_id,
                        {
                            "status": (
                                "completed"
                                if executed_command.rstrip(" \t")
                                == reviewed_command.rstrip(" \t")
                                else "edited"
                            ),
                            "executed_command": executed_command,
                            "cwd_before": session.cwd,
                            "cwd_after": session.cwd,
                            "output": executed_output,
                            "exit_status": executed_status,
                        },
                    )
                else:
                    result.tool_result(
                        call_id,
                        {
                            "status": "cancelled",
                            "reason": "The user cancelled the proposal; it was not executed.",
                        },
                    )
            else:
                result.assistant(output)
        else:
            result.shell(sequence, command, session.cwd, output, status)

        index += 1

    if request:
        result.user(request)

    return result


def conversation_from_events(
    session: Session, request: str, fallback_text: str | None = None
) -> Conversation:
    """Build authoritative ask history from the plugin's in-memory event log."""
    result = Conversation()
    sequence = 0
    event_commands = {
        event.get("command", "") for event in session.events or []
        if event.get("type") == "shell"
    }
    # Scrollback remains useful for commands the user ran outside ask. It never
    # replaces an ask event, including a silent command such as `cd`.
    if fallback_text is not None:
        for command, output, status in entries(session, fallback_text):
            if not command.startswith("?") and command not in event_commands:
                sequence += 1
                result.shell(sequence, command, session.cwd, output, status)
    pending_call: tuple[str, str, str] | None = None
    for event_index, event in enumerate(session.events or [], start=1):
        if event.get("type") == "ask":
            result.user(event.get("request", ""))
            comment = event.get("assistant", "")
            command = event.get("command")
            resolution = event.get("resolution")
            result.assistant(comment)
            if command:
                call_id = event.get("call_id") or f"call_ask_shell_{event_index}"
                item_id = event.get("call_item_id")
                result.shell_call(
                    call_id, command, item_id if isinstance(item_id, str) else None
                )
                if resolution == "cancel":
                    result.tool_result(
                        call_id,
                        {
                            "status": "cancelled",
                            "reason": "The user cancelled the proposal; it was not executed.",
                        },
                    )
                else:
                    pending_call = (call_id, command, resolution or "completed")
        elif event.get("type") == "shell":
            if pending_call:
                call_id, proposed_command, resolution = pending_call
                executed_command = event.get("command", "")
                result.tool_result(
                    call_id,
                    {
                        "status": (
                            "edited"
                            if resolution == "edit" or executed_command != proposed_command
                            else "completed"
                        ),
                        "executed_command": executed_command,
                        "cwd_before": event.get("cwd_before", ""),
                        "cwd_after": event.get("cwd_after", ""),
                        "output": event.get("output", ""),
                        "exit_status": event.get("exit_status"),
                    },
                )
                pending_call = None
            else:
                sequence += 1
                result.shell(
                    sequence,
                    event.get("command", ""),
                    event.get("cwd_before", ""),
                    event.get("output", ""),
                    event.get("exit_status"),
                )
    if request:
        result.user(request)
    return result
