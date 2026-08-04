from __future__ import annotations

import argparse
import sys
from importlib.resources import files

from ask.app import App
from ask.errors import AskError
from ask.terminal.review import present
from ask.terminal.transcript import Session


def intercept_script() -> str:
    return files("ask").joinpath("intercept.zsh").read_text()


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="ask")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("initialize")
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
        if args.command == "initialize":
            print(intercept_script(), end="")
            return 0

        session = Session(
            args.previous_command, args.current_command, args.cwd, args.tty,
            args.previous_status, args.history_entry,
        )
        request = " ".join(args.request[1:] if args.request[:1] == ["--"] else args.request)
        proposal = App().request(session, request)

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
