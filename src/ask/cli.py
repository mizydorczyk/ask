import argparse
import json
import os
import re
import sys
from pathlib import Path
from uuid import uuid4

from ask.app import App
from ask.errors import AskError
from ask.terminal.progress import Progress
from ask.terminal.review import present
from ask.terminal.transcript import Session


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="ask")
    commands = root.add_subparsers(dest="command", required=True)
    request = commands.add_parser("request")
    snapshot = commands.add_parser("snapshot")

    for command in (request, snapshot):
        command.add_argument("--previous-command", required=True)
        command.add_argument("--current-command", required=True)
        command.add_argument("--cwd", required=True)
        command.add_argument("--tty", required=True)
        command.add_argument("--previous-status", type=int, required=True)
        command.add_argument("--terminal-program", required=True)
        command.add_argument("--history-entry", action="append", default=[])

    request.add_argument("request", nargs=argparse.REMAINDER)
    snapshot.add_argument("--output", required=True)
    snapshot.add_argument("request", nargs=argparse.REMAINDER)

    return root


def main() -> int:
    args = parser().parse_args()

    try:
        session = Session(
            args.previous_command,
            args.current_command,
            args.cwd,
            args.tty,
            args.previous_status,
            args.history_entry,
            args.terminal_program,
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

            print("done", end="")
            return 0

        print(present(session.tty, proposal.comment, proposal.command or ""), end="")

        return 0
    except (AskError, OSError) as error:
        print(f"ask: {error}", file=sys.stderr)

        return 1


def _request_text(parts: list[str]) -> str:
    return " ".join(parts[1:] if parts[:1] == ["--"] else parts)


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
