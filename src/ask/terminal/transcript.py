from __future__ import annotations

import secrets
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

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


def capture(tty: str) -> str:
    if sys.platform != "darwin":
        raise AskError("unsupported terminal platform")

    marker = f"__ASK_TERMINAL_BOUNDARY_{secrets.token_hex(16)}__"
    script = Path(__file__).with_name("capture.applescript").read_text()
    result = subprocess.run(
        ["/usr/bin/osascript", "-e", script, "--", tty, marker],
        capture_output=True,
        check=False,
    )

    if result.returncode:
        detail = result.stderr.decode(errors="replace").strip()

        if "-1743" in detail:
            raise AskError(
                "Terminal.app Automation access was denied; allow access in System Settings"
            )

        if "-600" in detail:
            raise AskError("Terminal.app is not running")

        if "64" in detail:
            raise AskError("no Terminal.app tab matches the invoking TTY")

        raise AskError(f"Terminal.app capture failed: {detail or 'no error details'}")

    text = result.stdout.decode()
    if text.count(marker) != 1:
        raise AskError("Terminal.app returned an invalid response")

    before, after = text.rstrip("\n").split(marker)

    return (
        before
        + (
            ""
            if not before or before.endswith("\n") or after.startswith("\n")
            else "\n"
        )
        + after
    )


def entries(session: Session, text: str) -> list[tuple[str, str, int | None]]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    current = session.current_command.rstrip(" \t")
    current_at = text.rfind(current)

    if current_at < 0:
        raise AskError("cannot find the current request in Terminal.app scrollback")

    line_start = text.rfind("\n", 0, current_at) + 1
    prompt = text[line_start:current_at]
    if not prompt:
        raise AskError("cannot identify the current Terminal.app prompt")

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

            if prefix == prompt or reviewed:
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


def reviewed_execution(
    output: str, previous_command: str
) -> tuple[str, str, str] | None:
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
    if not terminal_output and command.rstrip(" \t") != previous_command.rstrip(" \t"):
        return None

    return output[:proposal].rstrip("\n"), command, terminal_output


def conversation(session: Session, request: str, text: str) -> Conversation:
    result = Conversation()

    for sequence, (command, output, status) in enumerate(entries(session, text), 1):
        if command.startswith("?"):
            if output.lstrip().startswith("ask: "):
                continue

            result.user(command[1:].lstrip())

            reviewed = reviewed_execution(output, session.previous_command)
            if reviewed:
                comment, reviewed_command, reviewed_output = reviewed
                result.assistant(comment)
                result.shell(
                    sequence, reviewed_command, session.cwd, reviewed_output, status
                )
            else:
                result.assistant(output)
        else:
            result.shell(sequence, command, session.cwd, output, status)

    if request:
        result.user(request)

    return result
