import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

from ask.cli import _write_snapshot, main, parser


class CliTests(unittest.TestCase):
    def test_initialize_is_not_a_cli_command(self):
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit) as error:
            parser().parse_args(["initialize"])
        self.assertEqual(error.exception.code, 2)

    def test_snapshot_is_a_cli_command(self):
        args = parser().parse_args(
            [
                "snapshot",
                "--previous-command",
                "pwd",
                "--current-command",
                "ask snapshot",
                "--cwd",
                "/work",
                "--tty",
                "/dev/tty",
                "--previous-status",
                "0",
                "--terminal-program",
                "Terminal",
                "--output",
                "dataset/",
                "list files",
            ]
        )

        self.assertEqual(args.command, "snapshot")
        self.assertEqual(args.request, ["list files"])

    def test_snapshot_writes_a_new_terminal_named_json_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = _write_snapshot(directory + "/", "Terminal.app", {"input": []})

            self.assertEqual(path.parent, Path(directory))
            self.assertRegex(path.name, r"^Terminal\.app-[0-9a-f-]{36}\.json$")
            self.assertEqual(json.loads(path.read_text()), {"input": []})

    def test_file_like_snapshot_target_uses_its_parent_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            path = _write_snapshot(
                str(Path(directory) / "example.json"), "", {"input": []}
            )

            self.assertEqual(path.parent, Path(directory))
            self.assertRegex(path.name, r"^terminal-[0-9a-f-]{36}\.json$")

    def test_snapshot_command_writes_context_without_a_model_request(self):
        with tempfile.TemporaryDirectory() as directory:
            output = StringIO()
            app = Mock()
            app.snapshot.return_value = {"model": "test", "input": []}
            arguments = [
                "ask",
                "snapshot",
                "--previous-command",
                "",
                "--current-command",
                "ask snapshot",
                "--cwd",
                "/work",
                "--tty",
                "/dev/tty",
                "--previous-status",
                "0",
                "--terminal-program",
                "Terminal",
                "--output",
                directory + "/",
                "list files",
            ]

            with (
                patch("ask.cli.App", return_value=app),
                patch.object(sys, "argv", arguments),
                redirect_stdout(output),
            ):
                self.assertEqual(main(), 0)

            path = Path(output.getvalue().strip())
            self.assertEqual(json.loads(path.read_text()), app.snapshot.return_value)
            app.snapshot.assert_called_once()
