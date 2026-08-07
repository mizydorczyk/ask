import json
import os
import unittest
from unittest.mock import patch

from ask.conversation import Conversation
from ask.errors import AskError
from ask.openai.responses import (
    INSTRUCTIONS,
    MAX_OUTPUT_TOKENS,
    PROMPT_CACHE_KEY,
    REASONING_EFFORT,
    VERBOSITY,
    OpenAIResponsesModel,
    Usage,
    proposal,
    request,
)
from ask.tools import definitions


class FunctionCall:
    type = "function_call"

    def __init__(self, name: str, arguments: str) -> None:
        self.name = name
        self.arguments = arguments
        self.call_id = "call_native"
        self.id = "fc_native"


class Response:
    def __init__(self, output, output_text: str, usage=None) -> None:
        self.output = output
        self.output_text = output_text
        self.usage = usage


class InputTokenDetails:
    cached_tokens = 50
    cache_write_tokens = 25


class ResponseUsage:
    input_tokens = 200
    output_tokens = 20
    input_tokens_details = InputTokenDetails()


class RecordingResponses:
    def __init__(self, response: Response) -> None:
        self.response = response
        self.kwargs: dict[str, object] = {}

    def create(self, **kwargs: object) -> Response:
        self.kwargs = kwargs
        return self.response


class RecordingClient:
    def __init__(self, response: Response) -> None:
        self.responses = RecordingResponses(response)


class OpenAIResponsesTests(unittest.TestCase):
    def test_shell_history_maps_to_generic_function_items(self):
        conversation = Conversation()
        conversation.shell(1, "cargo test", "/work", "ok", 0)

        result = request(conversation, definitions())

        self.assertEqual(result["tools"][0]["name"], "shell")
        self.assertEqual(result["input"][1]["name"], "shell")
        self.assertEqual(
            json.loads(result["input"][1]["arguments"]),
            {"command": "cargo test"},
        )
        self.assertEqual(
            json.loads(result["input"][2]["output"]), {
                "status": "completed", "executed_command": "cargo test",
                "cwd_before": "/work", "cwd_after": "/work",
                "output": "ok", "exit_status": 0,
            }
        )
        self.assertEqual(result["input"][1]["call_id"], "call_shell_1")
        self.assertEqual(result["input"][1]["id"], "fc_call_shell_1")

    def test_shell_tool_has_only_a_command_and_rejects_a_cwd_argument(self):
        tool = definitions()[0]
        self.assertEqual(tool.parameters["required"], ["command"])
        self.assertEqual(set(tool.parameters["properties"]), {"command"})
        with self.assertRaises(AskError):
            proposal(Response([FunctionCall("shell", '{"command":"pwd","cwd":"/work"}')], ""))

    def test_request_caches_reusable_history_but_not_the_current_request(self):
        conversation = Conversation()
        conversation.user("first request")
        conversation.assistant("first response")
        conversation.user("current request")

        result = request(conversation, definitions())

        self.assertEqual(result["prompt_cache_key"], PROMPT_CACHE_KEY)
        self.assertEqual(result["prompt_cache_options"], {"mode": "explicit"})
        self.assertEqual(
            result["input"][0],
            {
                "type": "message",
                "role": "developer",
                "content": [{"type": "input_text", "text": INSTRUCTIONS}],
            },
        )
        self.assertEqual(
            result["input"][1]["content"][0]["prompt_cache_breakpoint"],
            {"mode": "explicit"},
        )
        self.assertEqual(
            result["input"][2],
            {
                "type": "message",
                "role": "assistant",
                "content": "first response",
            },
        )
        self.assertNotIn("prompt_cache_breakpoint", result["input"][3]["content"][0])

    @patch.dict(os.environ, {}, clear=True)
    def test_text_response_becomes_done_proposal(self):
        client = RecordingClient(
            Response(
                [],
                "`git status` shows the working tree.",
                ResponseUsage(),
            )
        )

        result = OpenAIResponsesModel(client).propose(Conversation(), definitions())

        self.assertEqual(result.kind, "done")
        self.assertEqual(result.comment, "`git status` shows the working tree.")
        self.assertEqual(client.responses.kwargs["model"], "gpt-5.6-luna")
        self.assertEqual(client.responses.kwargs["prompt_cache_key"], PROMPT_CACHE_KEY)
        self.assertEqual(
            client.responses.kwargs["prompt_cache_options"], {"mode": "explicit"}
        )
        self.assertEqual(
            client.responses.kwargs["reasoning"], {"effort": REASONING_EFFORT}
        )
        self.assertEqual(client.responses.kwargs["text"], {"verbosity": VERBOSITY})
        self.assertEqual(
            client.responses.kwargs["max_output_tokens"], MAX_OUTPUT_TOKENS
        )
        self.assertFalse(client.responses.kwargs["parallel_tool_calls"])
        self.assertEqual(
            OpenAIResponsesModel(client).last_usage,
            None,
        )

    def test_model_parameters_can_be_set_with_environment_variables(self):
        client = RecordingClient(Response([], "ok"))

        with patch.dict(
            os.environ,
            {
                "ASK_MODEL": "custom-model",
                "ASK_REASONING_EFFORT": "high",
                "ASK_VERBOSITY": "medium",
                "ASK_MAX_OUTPUT_TOKENS": "1024",
            },
        ):
            OpenAIResponsesModel(client).propose(Conversation(), definitions())

        self.assertEqual(client.responses.kwargs["model"], "custom-model")
        self.assertEqual(client.responses.kwargs["reasoning"], {"effort": "high"})
        self.assertEqual(client.responses.kwargs["text"], {"verbosity": "medium"})
        self.assertEqual(client.responses.kwargs["max_output_tokens"], 1024)

    def test_model_parameters_can_be_set_in_code(self):
        client = RecordingClient(Response([], "ok"))
        model = OpenAIResponsesModel(
            client,
            model="custom-model",
            reasoning_effort="medium",
            verbosity="high",
            max_output_tokens=2048,
        )

        model.propose(Conversation(), definitions())

        self.assertEqual(client.responses.kwargs["model"], "custom-model")
        self.assertEqual(client.responses.kwargs["reasoning"], {"effort": "medium"})
        self.assertEqual(client.responses.kwargs["text"], {"verbosity": "high"})
        self.assertEqual(client.responses.kwargs["max_output_tokens"], 2048)

    def test_request_parameters_match_the_payload_sent_to_openai(self):
        client = RecordingClient(Response([], "ok"))
        model = OpenAIResponsesModel(client)
        conversation = Conversation()
        conversation.user("list files")

        snapshot = model.request_parameters(conversation, definitions())
        model.propose(conversation, definitions())

        self.assertEqual(snapshot, client.responses.kwargs)

    def test_invalid_max_output_tokens_is_a_friendly_error(self):
        for value in ("many", "0", "-1"):
            with (
                self.subTest(value=value),
                patch.dict(os.environ, {"ASK_MAX_OUTPUT_TOKENS": value}),
                self.assertRaisesRegex(AskError, "must be a positive integer"),
            ):
                OpenAIResponsesModel()

    def test_response_usage_exposes_cache_metrics(self):
        client = RecordingClient(Response([], "ok", ResponseUsage()))
        model = OpenAIResponsesModel(client)

        model.propose(Conversation(), definitions())

        self.assertEqual(model.last_usage, Usage(200, 20, 50, 25))

    def test_shell_call_becomes_review_proposal(self):
        client = RecordingClient(
            Response(
                [FunctionCall("shell", '{"command":"git status"}')],
                "Shows the working tree.",
            )
        )

        result = OpenAIResponsesModel(client).propose(Conversation(), definitions())

        self.assertEqual(result.kind, "review")
        self.assertEqual(result.comment, "Shows the working tree.")
        self.assertEqual(result.command, "git status")
        self.assertEqual(result.call_id, "call_native")
        self.assertEqual(result.call_item_id, "fc_native")

    def test_shell_call_without_text_gets_a_review_prompt(self):
        result = proposal(
            Response(
                [FunctionCall("shell", '{"command":"git status"}')],
                "",
            )
        )

        self.assertEqual(result.comment, "Review this command.")

    def test_instructions_require_commands_to_be_function_calls(self):
        self.assertIn("must be the shell function call", INSTRUCTIONS)
        self.assertIn("canceled proposal", INSTRUCTIONS)

    def test_invalid_model_proposals_are_rejected(self):
        cases = [
            Response([], ""),
            Response([FunctionCall("shell", "not json")], "text"),
            Response([FunctionCall("shell", "{}")], "text"),
            Response([FunctionCall("other", "{}")], "text"),
            Response(
                [
                    FunctionCall("shell", '{"command":"one"}'),
                    FunctionCall("shell", '{"command":"two"}'),
                ],
                "text",
            ),
        ]

        for response in cases:
            with self.subTest(response=response), self.assertRaises(AskError):
                proposal(response)

    def test_missing_api_key_is_a_friendly_error(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            self.assertRaisesRegex(AskError, "OPENAI_API_KEY is not set"),
        ):
            OpenAIResponsesModel().propose(Conversation(), definitions())
