import json
import os
from dataclasses import dataclass
from typing import Any

from openai import (
    APIConnectionError,
    APIStatusError,
    AuthenticationError,
    OpenAI,
    OpenAIError,
    PermissionDeniedError,
    RateLimitError,
)

from ask.conversation import Conversation, Message, ToolCall, ToolResult
from ask.errors import AskError
from ask.model import Proposal
from ask.tools import ToolDefinition

MODEL = "gpt-5.6-luna"
PROMPT_CACHE_KEY = "ask:terminal-command-assistant:v1"
REASONING_EFFORT = "low"
VERBOSITY = "low"
MAX_OUTPUT_TOKENS = 1024
INSTRUCTIONS = """You are ask, a concise assistant for a Zsh terminal.

Use the terminal event history supplied in the conversation as context. For an
explanation or when a command would not help, reply with concise plain text.
When the user needs one shell command, make exactly one shell function call
with the command, then briefly explain what the command does. The command runs
in the live Zsh shell's current working directory. The function call is only a
proposal: never claim that it has run. Do not make more than one function call.

ask is for terminal tasks: creating, fixing, explaining, and improving shell
commands. For requests to edit source code, write documentation, or have
general-purpose chat, briefly explain that the request is outside ask's scope
and do not make a shell function call.

Never put a shell command, code block, or copy-pasteable shell snippet in plain
text. If your response includes a command, it must be the shell function call
and not message text. A canceled proposal in the conversation was not executed.
When the next user message adds a constraint to a canceled proposal, revise that
proposal directly instead of asking for information the user has already given.
"""


def request(conversation: Conversation, tools: list[ToolDefinition]) -> dict[str, Any]:
    input_items: list[dict[str, Any]] = [
        {
            "type": "message",
            "role": "developer",
            "content": [{"type": "input_text", "text": INSTRUCTIONS}],
        }
    ]
    user_message_indexes = [
        index
        for index, turn in enumerate(conversation.turns)
        if isinstance(turn, Message) and turn.role == "user"
    ]
    cache_breakpoints = set(user_message_indexes[:-1][-4:])

    for index, turn in enumerate(conversation.turns):
        if isinstance(turn, Message):
            if turn.role == "assistant":
                content: str | list[dict[str, Any]] = turn.content
            else:
                input_text: dict[str, Any] = {
                    "type": "input_text",
                    "text": turn.content,
                }
                if index in cache_breakpoints:
                    input_text["prompt_cache_breakpoint"] = {"mode": "explicit"}
                content = [input_text]
            input_items.append(
                {
                    "type": "message",
                    "role": turn.role,
                    "content": content,
                }
            )
        elif isinstance(turn, ToolCall):
            input_items.append(
                {
                    "type": "function_call",
                    "id": f"fc_{turn.id}",
                    "call_id": turn.id,
                    "name": turn.tool,
                    "arguments": json.dumps(turn.arguments, separators=(",", ":")),
                    "status": "completed",
                }
            )
        elif isinstance(turn, ToolResult):
            input_items.append(
                {
                    "type": "function_call_output",
                    "call_id": turn.call_id,
                    "output": json.dumps(turn.output, separators=(",", ":")),
                }
            )

    return {
        "input": input_items,
        "prompt_cache_key": PROMPT_CACHE_KEY,
        "prompt_cache_options": {"mode": "explicit"},
        "tools": [
            {
                "type": "function",
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
                "strict": True,
            }
            for tool in tools
        ],
    }


class OpenAIResponsesModel:
    def __init__(
        self,
        client: Any | None = None,
        model: str | None = None,
        reasoning_effort: str | None = None,
        verbosity: str | None = None,
        max_output_tokens: int | None = None,
    ) -> None:
        self._client = client
        self._model = model or os.environ.get("ASK_MODEL") or MODEL
        self._reasoning_effort = (
            reasoning_effort
            or os.environ.get("ASK_REASONING_EFFORT")
            or REASONING_EFFORT
        )
        self._verbosity = verbosity or os.environ.get("ASK_VERBOSITY") or VERBOSITY
        self._max_output_tokens = _max_tokens(max_output_tokens)
        self.last_usage: Usage | None = None

    def request_parameters(
        self, conversation: Conversation, tools: list[ToolDefinition]
    ) -> dict[str, Any]:
        """Return the exact keyword arguments used for a Responses API call."""
        return {
            "model": self._model,
            "reasoning": {"effort": self._reasoning_effort},
            "text": {"verbosity": self._verbosity},
            "max_output_tokens": self._max_output_tokens,
            "parallel_tool_calls": False,
            **request(conversation, tools),
        }

    def propose(
        self, conversation: Conversation, tools: list[ToolDefinition]
    ) -> Proposal:
        self.last_usage = None
        try:
            response = self._responses().create(
                **self.request_parameters(conversation, tools)
            )
        except AuthenticationError as error:
            raise AskError(
                "OpenAI authentication failed; check OPENAI_API_KEY"
            ) from error
        except PermissionDeniedError as error:
            raise AskError(
                "OpenAI API key does not have permission for this request"
            ) from error
        except RateLimitError as error:
            raise AskError("OpenAI rate limit reached; try again shortly") from error
        except APIConnectionError as error:
            raise AskError(
                "cannot connect to OpenAI; check your network connection"
            ) from error
        except APIStatusError as error:
            raise AskError(
                f"OpenAI request failed (status {error.status_code})"
            ) from error
        except OpenAIError as error:
            raise AskError("OpenAI request failed") from error

        self.last_usage = usage(response)
        return proposal(response)

    def _responses(self) -> Any:
        if self._client is None:
            if not os.environ.get("OPENAI_API_KEY"):
                raise AskError("OPENAI_API_KEY is not set")
            self._client = OpenAI()

        return self._client.responses


def _max_tokens(value: int | None) -> int:
    raw_value: int | str = (
        value
        if value is not None
        else os.environ.get("ASK_MAX_OUTPUT_TOKENS", str(MAX_OUTPUT_TOKENS))
    )

    try:
        result = int(raw_value)
    except (TypeError, ValueError) as error:
        raise AskError("ASK_MAX_OUTPUT_TOKENS must be a positive integer") from error

    if result < 1:
        raise AskError("ASK_MAX_OUTPUT_TOKENS must be a positive integer")
    return result


def proposal(response: Any) -> Proposal:
    calls = [item for item in response.output if item.type == "function_call"]
    comment = response.output_text.strip()

    if not calls:
        if not comment:
            raise AskError("OpenAI returned an empty response")
        return Proposal("done", comment)

    if len(calls) != 1 or calls[0].name != "shell":
        raise AskError("OpenAI returned an unsupported command proposal")

    try:
        arguments = json.loads(calls[0].arguments)
    except json.JSONDecodeError as error:
        raise AskError("OpenAI returned an invalid command proposal") from error

    command = arguments.get("command") if isinstance(arguments, dict) else None
    if not isinstance(arguments, dict) or set(arguments) != {"command"}:
        raise AskError("OpenAI returned an invalid command proposal")
    if not isinstance(command, str) or not command.strip():
        raise AskError("OpenAI returned a command proposal without a command")

    call_id = getattr(calls[0], "call_id", None)
    if not isinstance(call_id, str) or not call_id:
        call_id = None
    item_id = getattr(calls[0], "id", None)
    if not isinstance(item_id, str) or not item_id:
        item_id = None
    return Proposal(
        "review", comment or "Review this command.", command, call_id, item_id
    )


@dataclass(frozen=True)
class Usage:
    input_tokens: int | None
    output_tokens: int | None
    cached_tokens: int | None
    cache_write_tokens: int | None


def usage(response: Any) -> Usage | None:
    result = getattr(response, "usage", None)
    if result is None:
        return None

    details = getattr(result, "input_tokens_details", None)
    return Usage(
        getattr(result, "input_tokens", None),
        getattr(result, "output_tokens", None),
        getattr(details, "cached_tokens", None),
        getattr(details, "cache_write_tokens", None),
    )
