import unittest
from pathlib import Path

from jinja2.exceptions import TemplateError
from transformers.utils.chat_template_utils import render_jinja_template

TEMPLATE = (
    Path(__file__).parents[1] / "gemma-4-e4b-it-ask" / "chat_template_training.jinja"
).read_text()


def render(messages, *, add_generation_prompt=False, tools=None, **kwargs):
    rendered, indices = render_jinja_template(
        conversations=[messages],
        chat_template=TEMPLATE,
        return_assistant_tokens_mask=True,
        add_generation_prompt=add_generation_prompt,
        bos_token="<bos>",
        tools=tools,
        **kwargs,
    )
    text = rendered[0]
    return text, [text[int(start):int(end)] for start, end in indices[0]]


class GemmaChatTemplateTests(unittest.TestCase):
    def test_assistant_reply_is_marked_for_assistant_only_loss(self):
        _, generated = render(
            [
                {"role": "user", "content": "List files."},
                {"role": "assistant", "content": "I will list them."},
            ]
        )

        self.assertEqual(generated, ["I will list them."])

    def test_tool_call_and_handoff_are_marked_but_tool_response_is_not(self):
        _, generated = render(
            [
                {"role": "user", "content": "List files."},
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "function": {
                                "name": "list_files",
                                "arguments": {"path": "."},
                            },
                        }
                    ],
                },
                {"role": "tool", "tool_call_id": "call_1", "content": "README.md"},
                {"role": "assistant", "content": "README.md is present."},
            ]
        )

        self.assertIn(
            '<|tool_call>call:list_files{path:<|"|>.<|"|>}<tool_call|>', generated
        )
        self.assertIn("<|tool_response>", generated)
        self.assertIn("README.md is present.", generated)
        self.assertNotIn('response:list_files{value:<|"|>README.md<|"|>}', generated)

    def test_context_and_generation_prompt_are_not_marked_as_assistant_output(self):
        _, generated = render(
            [
                {"role": "system", "content": "Follow the shell safety policy."},
                {"role": "user", "content": "List files."},
            ],
            add_generation_prompt=True,
        )

        self.assertEqual(generated, [])

    def test_official_gemma_function_calling_example_keeps_tool_schema_as_context(self):
        weather_tool = {
            "type": "function",
            "function": {
                "name": "get_n_day_weather_forecast",
                "description": "Get an N-day weather forecast",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string", "description": "The city and state."},
                        "num_days": {"type": "integer", "description": "Number of days."},
                    },
                    "required": ["location", "num_days"],
                },
            },
        }

        rendered, generated = render([
            {"role": "user", "content": "What is the weather in Boston for the next three days?"},
        ], tools=[weather_tool], add_generation_prompt=True)

        self.assertIn("declaration:get_n_day_weather_forecast", rendered)
        self.assertIn("<|turn>model\n", rendered)
        self.assertEqual(generated, [])

    def test_reasoning_and_answer_are_marked_as_assistant_output(self):
        _, generated = render([
            {"role": "user", "content": "What is 2 + 2?"},
            {
                "role": "assistant",
                "reasoning_content": "Add the two numbers.",
                "content": "4",
            },
        ])

        self.assertEqual(generated, [
            "<|channel>thought\nAdd the two numbers.\n<channel|>",
            "4",
        ])

    def test_multiple_tool_results_keep_each_payload_outside_assistant_loss(self):
        _, generated = render([
            {"role": "user", "content": "Inspect the repository."},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": "call_1", "function": {"name": "list_files", "arguments": {}}},
                    {"id": "call_2", "function": {"name": "read_file", "arguments": {"path": "README.md"}}},
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "README.md\nsrc"},
            {"role": "tool", "tool_call_id": "call_2", "content": "# ask"},
            {"role": "assistant", "content": "The repository contains the ask CLI."},
        ])

        self.assertEqual(generated.count("<|tool_response>"), 2)
        self.assertIn("The repository contains the ask CLI.", generated)
        self.assertFalse(any("README.md\nsrc" in span or "# ask" in span for span in generated))

    def test_official_multimodal_message_example_keeps_user_parts_outside_assistant_loss(self):
        rendered, generated = render([
            {
                "role": "user",
                "content": [
                    {"type": "image", "url": "https://example.com/cat.jpeg"},
                    {"type": "text", "text": "What is shown in this image?"},
                ],
            },
        ], add_generation_prompt=True)

        self.assertIn("<|image|>What is shown in this image?", rendered)
        self.assertEqual(generated, [])

    def test_unanswered_tool_call_marks_the_handoff_token_for_training(self):
        _, generated = render([
            {"role": "user", "content": "List files."},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "call_1",
                    "function": {"name": "list_files", "arguments": {}},
                }],
            },
        ])

        self.assertEqual(generated, [
            "<|tool_call>call:list_files{}<tool_call|>",
            "<|tool_response>",
        ])

    def test_multimodal_assistant_content_is_marked_for_training(self):
        _, generated = render([
            {"role": "user", "content": "Describe the image."},
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "It is a cat."},
                    {"type": "image", "url": "https://example.com/cat.jpeg"},
                ],
            },
        ])

        self.assertEqual(generated, ["It is a cat.<|image|>"])

    def test_string_tool_arguments_are_rejected(self):
        with self.assertRaisesRegex(TemplateError, "arguments must be a JSON object"):
            render([
                {"role": "user", "content": "List files."},
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": "call_1",
                        "function": {"name": "list_files", "arguments": "{}"},
                    }],
                },
            ])
