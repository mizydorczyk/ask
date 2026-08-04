import unittest

from ask.conversation import Conversation, ToolCall, ToolResult


class ConversationTests(unittest.TestCase):
    def test_shell_execution_is_a_call_and_result(self):
        conversation = Conversation()
        conversation.shell(1, "cargo test", "/work", "ok", 0)

        self.assertEqual(conversation.turns, [
            ToolCall("shell_1", "shell", {"command": "cargo test", "cwd": "/work"}),
            ToolResult("shell_1", {"output": "ok", "exit_status": 0}),
        ])
