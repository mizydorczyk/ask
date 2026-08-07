import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

from ask.cli import (
    _captured_output,
    _encode_event,
    _events,
    _write_snapshot,
    main,
    parser,
)


class CliTests(unittest.TestCase):
    def test_event_records_round_trip_without_writing_them_to_disk(self):
        event = {
            "type": "shell",
            "command": "cd next",
            "cwd_before": "/work",
            "cwd_after": "/work/next",
            "exit_status": 0,
            "output": "",
        }
        self.assertEqual(_events([_encode_event(event)]), [event])

    @patch("ask.cli.output_after_review", return_value="Created package.")
    def test_event_captures_reviewed_command_output_when_a_tty_is_available(self, _):
        output = StringIO()
        with (
            patch.object(
                sys,
                "argv",
                [
                    "ask",
                    "event",
                    "--command",
                    "cargo new demo",
                    "--cwd-before",
                    "/work",
                    "--cwd-after",
                    "/work",
                    "--exit-status",
                    "0",
                    "--tty",
                    "/dev/ttys001",
                ],
            ),
            redirect_stdout(output),
        ):
            self.assertEqual(main(), 0)

        self.assertEqual(_events([output.getvalue()])[0]["output"], "Created package.")

    @patch("ask.cli.output_after_review", return_value="Created package.")
    def test_event_uses_the_original_review_command_to_capture_edited_output(
        self, capture
    ):
        output = StringIO()
        with (
            patch.object(
                sys,
                "argv",
                [
                    "ask",
                    "event",
                    "--command",
                    "cargo new browser8000",
                    "--review-command",
                    "cargo new browser9000",
                    "--cwd-before",
                    "/work",
                    "--cwd-after",
                    "/work",
                    "--exit-status",
                    "0",
                    "--tty",
                    "/dev/ttys001",
                ],
            ),
            redirect_stdout(output),
        ):
            self.assertEqual(main(), 0)

        capture.assert_called_once_with("/dev/ttys001", "cargo new browser9000")
        self.assertEqual(
            _events([output.getvalue()])[0]["command"], "cargo new browser8000"
        )

    @patch("ask.cli.sleep")
    @patch("ask.cli.output_after_review", return_value="Created package.")
    def test_event_output_uses_one_delayed_scrollback_capture(self, _, sleep):
        self.assertEqual(
            _captured_output("/dev/ttys001", "cargo new demo", "cargo new demo"),
            "Created package.",
        )
        sleep.assert_called_once_with(0.1)

    @patch(
        "ask.cli.output_after_review",
        return_value="prompt % cargo new browser8000\nCreated package.\n   ",
    )
    def test_event_output_removes_the_echoed_actual_command_and_terminal_padding(
        self, _
    ):
        self.assertEqual(
            _captured_output(
                "/dev/ttys001", "cargo new browser9000", "cargo new browser8000"
            ),
            "Created package.",
        )

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
