import argparse
import os
import sys

from ask.app import App
from ask.errors import AskError
from ask.terminal.progress import Progress
from ask.terminal.review import present
from ask.terminal.transcript import Session


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="ask")
    commands = root.add_subparsers(dest="command", required=True)
    request = commands.add_parser("request")
    request.add_argument("--previous-command", required=True)
    request.add_argument("--current-command", required=True)
    request.add_argument("--cwd", required=True)
    request.add_argument("--tty", required=True)
    request.add_argument("--previous-status", type=int, required=True)
    request.add_argument("--terminal-program", required=True)
    request.add_argument("--history-entry", action="append", default=[])
    request.add_argument("request", nargs=argparse.REMAINDER)

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
        )
        request = " ".join(
            args.request[1:] if args.request[:1] == ["--"] else args.request
        )
        app = App()
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
