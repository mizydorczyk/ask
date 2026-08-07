import argparse
import base64
import json
import os
import re
import sys
from pathlib import Path
from time import sleep
from uuid import uuid4

from ask.app import App
from ask.errors import AskError
from ask.terminal.progress import Progress
from ask.terminal.review import present
from ask.terminal.transcript import Session, output_after_review


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="ask")
    commands = root.add_subparsers(dest="command", required=True)
    request = commands.add_parser("request")
    snapshot = commands.add_parser("snapshot")
    event = commands.add_parser("event")

    for command in (request, snapshot):
        command.add_argument("--previous-command", required=True)
        command.add_argument("--current-command", required=True)
        command.add_argument("--cwd", required=True)
        command.add_argument("--tty", required=True)
        command.add_argument("--previous-status", type=int, required=True)
        command.add_argument("--terminal-program", required=True)
        command.add_argument("--history-entry", action="append", default=[])
        # Opaque, base64-encoded event records passed only by the Zsh plugin.
        command.add_argument("--event", action="append", default=[])

    request.add_argument("request", nargs=argparse.REMAINDER)
    snapshot.add_argument("--output", required=True)
    snapshot.add_argument("request", nargs=argparse.REMAINDER)
    event.add_argument("--command", dest="event_command", required=True)
    event.add_argument("--review-command")
    event.add_argument("--cwd-before", required=True)
    event.add_argument("--cwd-after", required=True)
    event.add_argument("--exit-status", type=int, required=True)
    event.add_argument("--tty")

    return root


def main() -> int:
    args = parser().parse_args()

    try:
        if args.command == "event":
            output = _captured_output(
                args.tty, args.review_command or args.event_command, args.event_command
            )
            print(
                _encode_event(
                    {
                        "type": "shell",
                        "command": args.event_command,
                        "cwd_before": args.cwd_before,
                        "cwd_after": args.cwd_after,
                        "exit_status": args.exit_status,
                        "output": output,
                    }
                ),
                end="",
            )
            return 0

        session = Session(
            args.previous_command,
            args.current_command,
            args.cwd,
            args.tty,
            args.previous_status,
            args.history_entry,
            args.terminal_program,
            _events(args.event),
        )

        request = _request_text(args.request)
        app = App()

        if args.command == "snapshot":
            path = _write_snapshot(
                args.output, session.terminal_program, app.snapshot(session, request)
            )
            print(path)
            return 0

        progress = Progress(session.tty)
        try:
            proposal = app.request(session, request, progress.start)
        finally:
            progress.stop()

        if os.environ.get("ASK_DEBUG") == "1" and app.last_metrics:
            _write_metrics(session.tty, app.last_metrics)

        if proposal.kind == "done":
            with open(session.tty, "wb", buffering=0) as tty:
                tty.write((proposal.comment + "\n").encode())

            print("done")
            print(_event_update(request, session, proposal, "done"), end="")
            return 0

        resolution = present(session.tty, proposal.comment, proposal.command or "")
        action, _, command = resolution.partition("\n")
        print(action)
        print(_event_update(request, session, proposal, action))
        print(command, end="")

        return 0
    except (AskError, OSError) as error:
        print(f"ask: {error}", file=sys.stderr)

        return 1


def _request_text(parts: list[str]) -> str:
    return " ".join(parts[1:] if parts[:1] == ["--"] else parts)


def _events(values: list[str]) -> list[dict]:
    result: list[dict] = []

    for value in values:
        try:
            padded = value + "=" * (-len(value) % 4)
            event = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise AskError("invalid ask event context") from error
        if not isinstance(event, dict):
            raise AskError("invalid ask event context")
        result.append(event)

    return result


def _captured_output(
    tty: str | None, review_command: str, executed_command: str
) -> str:
    """Wait briefly for Terminal.app to publish output to its scrollback."""

    if not tty:
        return ""

    # A single delayed read gives Terminal.app time to publish scrollback without
    # repeatedly launching osascript for silent commands such as `rm`.
    sleep(0.1)

    try:
        return _without_echoed_command(
            output_after_review(tty, review_command), executed_command
        )
    except (AskError, OSError):
        return ""


def _without_echoed_command(output: str, command: str) -> str:
    first_line, separator, remainder = output.partition("\n")
    if separator and first_line.rstrip().endswith(command):
        output = remainder
    return output.rstrip()


def _event_update(request: str, session: Session, proposal, resolution: str) -> str:
    event = {
        "type": "ask",
        "request": request,
        "cwd": session.cwd,
        "assistant": proposal.comment,
        "command": proposal.command,
        "call_id": proposal.call_id,
        "call_item_id": proposal.call_item_id,
        "resolution": resolution,
    }
    return _encode_event(event)


def _encode_event(event: dict) -> str:
    return (
        base64.urlsafe_b64encode(json.dumps(event, separators=(",", ":")).encode())
        .decode("ascii")
        .rstrip("=")
    )


def _write_snapshot(output: str, terminal_program: str, payload: object) -> Path:
    target = Path(output).expanduser()
    directory = target if target.is_dir() or output.endswith(os.sep) else target.parent
    directory.mkdir(parents=True, exist_ok=True)
    terminal = re.sub(r"[^A-Za-z0-9._-]+", "-", terminal_program).strip(".-")
    terminal = terminal or "terminal"

    while True:
        path = directory / f"{terminal}-{uuid4()}.json"

        try:
            with path.open("x", encoding="utf-8") as snapshot:
                json.dump(payload, snapshot, ensure_ascii=False, indent=2)
                snapshot.write("\n")
        except FileExistsError:
            continue

        return path


def _write_metrics(tty_path: str, metrics) -> None:
    usage = metrics.usage
    tokens = ""

    if usage:
        tokens = (
            f"  input {usage.input_tokens}  output {usage.output_tokens}"
            f"  cached {usage.cached_tokens}  cache writes {usage.cache_write_tokens}"
        )

    text = (
        f"\x1b[38;5;245mask: context {metrics.context_seconds:.2f}s"
        f"  model {metrics.model_seconds:.2f}s  total {metrics.total_seconds:.2f}s"
        f"{tokens}\x1b[0m\n"
    )

    with open(tty_path, "wb", buffering=0) as tty:
        tty.write(text.encode())
