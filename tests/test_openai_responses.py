import json
import unittest

from ask.conversation import Conversation
from ask.openai.responses import request
from ask.tools import definitions


class OpenAIResponsesTests(unittest.TestCase):
    def test_shell_history_maps_to_generic_function_items(self):
        conversation = Conversation()
        conversation.shell(1, "cargo test", "/work", "ok", 0)

        result = request(conversation, definitions())

        self.assertEqual(result["tools"][0]["name"], "shell")
        self.assertEqual(result["input"][0]["name"], "shell")
        self.assertEqual(json.loads(result["input"][0]["arguments"]), {"command": "cargo test", "cwd": "/work"})
        self.assertEqual(json.loads(result["input"][1]["output"]), {"output": "ok", "exit_status": 0})
