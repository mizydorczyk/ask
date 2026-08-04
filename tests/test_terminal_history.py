import unittest
from unittest.mock import patch

from ask.conversation import Message, ToolCall, ToolResult
from ask.terminal.transcript import Session, conversation


class TerminalHistoryTests(unittest.TestCase):
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
                "shell_1",
                "shell",
                {"command": 'printf "Hello\\n"', "cwd": "/work"},
            ),
            ToolResult("shell_1", {"output": "Hello", "exit_status": 0}),
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
            Message(
                "assistant",
                "Creates a project.\n\n"
                "The user canceled the proposed command: cargo new test-project\n"
                "Treat a later constraint as a request to revise this proposal; "
                "do not assume it was executed.",
            ),
        ])
