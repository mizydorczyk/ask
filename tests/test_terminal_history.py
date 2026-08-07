import os
import subprocess
import unittest
from unittest.mock import patch

from ask.conversation import Message, ToolCall, ToolResult
from ask.errors import AskError
from ask.terminal.transcript import (
    Session,
    capture,
    conversation,
    entries,
    output_after_review,
)


class TerminalHistoryTests(unittest.TestCase):
    @patch("ask.terminal.transcript.subprocess.run")
    @patch.dict(os.environ, {"TMUX_PANE": "%12"}, clear=True)
    def test_capture_reads_the_current_tmux_pane(self, run):
        run.return_value = subprocess.CompletedProcess(
            [], 0, stdout=b"prompt % pwd\n/work\n", stderr=b""
        )

        self.assertEqual(capture(), "prompt % pwd\n/work\n")
        run.assert_called_once_with(
            ["tmux", "capture-pane", "-p", "-J", "-S", "-", "-t", "%12"],
            capture_output=True,
            check=False,
        )

    @patch.dict(os.environ, {}, clear=True)
    def test_capture_requires_a_tmux_pane(self):
        with self.assertRaisesRegex(AskError, "must run inside a tmux pane"):
            capture()

    @patch("ask.terminal.transcript.subprocess.run", side_effect=FileNotFoundError)
    @patch.dict(os.environ, {"TMUX_PANE": "%12"}, clear=True)
    def test_capture_explains_when_tmux_is_unavailable(self, _):
        with self.assertRaisesRegex(AskError, "tmux is required"):
            capture()

    @patch("ask.terminal.transcript.subprocess.run")
    @patch.dict(os.environ, {"TMUX_PANE": "%12"}, clear=True)
    def test_capture_reports_tmux_failures(self, run):
        run.return_value = subprocess.CompletedProcess(
            [], 1, stdout=b"", stderr=b"can't find pane: %12\n"
        )

        with self.assertRaisesRegex(AskError, "tmux capture failed: can't find pane"):
            capture()

    @patch("ask.terminal.transcript.capture")
    def test_output_after_review_uses_the_latest_matching_review(self, capture):
        capture.return_value = (
            "> cargo new demo\nenter run  tab edit  esc cancel\nold\n"
            "> cargo new demo\nenter run  tab edit  esc cancel\nCreated package.\n"
        )

        self.assertEqual(output_after_review("cargo new demo"), "Created package.")
    def test_entries_keeps_history_when_the_prompt_directory_changes(self):
        session = Session(
            "? Why it failed?",
            "ask snapshot --output dataset",
            "/work/Development",
            "/dev/tty",
            0,
            [
                "? Hi",
                "? Name it browser9000, but create it in Development folder",
                "? Why it failed?",
            ],
        )
        text = (
            "miz@mac ~ % ? Hi\n"
            "Hi! How can I help with your terminal?\n"
            "miz@mac ~ % ? Name it browser9000, but create it in Development folder\n"
            "Review this command.\n"
            "> cd Development && cargo new browser9000\n"
            "enter run  tab edit  esc cancel\n"
            "    Creating binary (application) `browser9000` package\n"
            "error: destination `/Users/miz/Development/browser9000` already exists\n"
            "miz@mac Development % ? Why it failed?\n"
            "Please provide the command you ran and its error output.\n"
            "miz@mac Development % ask snapshot --output dataset"
        )

        result = entries(session, text)

        self.assertEqual([command for command, _, _ in result], session.history)
        self.assertIn("destination", result[1][1])

    def test_reviewed_command_becomes_a_shell_execution(self):
        output = 'Prints a greeting.\n> printf "Hello\\n"\nenter run  tab edit  esc cancel\nHello'
        session = Session(
            'printf "Hello\\n"', "? greet me", "/work", "/dev/tty", 0, []
        )

        with patch(
            "ask.terminal.transcript.entries",
            return_value=[("? greet me", output, 0)],
        ):
            result = conversation(session, "", "")

        self.assertEqual(result.turns, [
            Message("user", "greet me"),
            Message("assistant", "Prints a greeting."),
            ToolCall(
                "call_ask_shell_1",
                "shell",
                {"command": 'printf "Hello\\n"'},
            ),
            ToolResult("call_ask_shell_1", {
                "status": "completed", "executed_command": 'printf "Hello\\n"',
                "cwd_before": "/work", "cwd_after": "/work",
                "output": "Hello", "exit_status": 0,
            }),
        ])

    def test_canceled_review_is_retained_as_unexecuted_context(self):
        output = 'Creates a project.\n> cargo new test-project\nenter run  tab edit  esc cancel\n'
        session = Session(
            "? do not create a git repo",
            "? create a project",
            "/work",
            "/dev/tty",
            0,
            [],
        )

        with patch(
            "ask.terminal.transcript.entries",
            return_value=[("? create a project", output, 0)],
        ):
            result = conversation(session, "", "")

        self.assertEqual(result.turns, [
            Message("user", "create a project"),
            Message("assistant", "Creates a project."),
            ToolCall("call_ask_shell_1", "shell", {"command": "cargo new test-project"}),
            ToolResult("call_ask_shell_1", {
                "status": "cancelled",
                "reason": "The user cancelled the proposal; it was not executed.",
            }),
        ])

    def test_edited_review_uses_the_command_that_was_run(self):
        output = (
            "Creates a project.\n> cargo new my-rust-project\n"
            "enter run  tab edit  esc cancel\n"
        )
        session = Session(
            "cargo new Development/browser9000",
            "? next request",
            "/work",
            "/dev/tty",
            0,
            [],
        )

        with patch(
            "ask.terminal.transcript.entries",
            return_value=[
                ("? create a project", output, None),
                ("cargo new Development/browser9000", "Created package.", 0),
            ],
        ):
            result = conversation(session, "", "")

        self.assertEqual(result.turns, [
            Message("user", "create a project"),
            Message("assistant", "Creates a project."),
            ToolCall(
                "call_ask_shell_1",
                "shell",
                {"command": "cargo new my-rust-project"},
            ),
            ToolResult(
                "call_ask_shell_1", {
                    "status": "edited",
                    "executed_command": "cargo new Development/browser9000",
                    "cwd_before": "/work", "cwd_after": "/work",
                    "output": "Created package.", "exit_status": 0,
                }
            ),
        ])
