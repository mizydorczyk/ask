from __future__ import annotations

import json
from typing import Any

from ask.conversation import Conversation, Message, ToolCall, ToolResult
from ask.tools import ToolDefinition


def request(conversation: Conversation, tools: list[ToolDefinition]) -> dict[str, Any]:
    input_items: list[dict[str, Any]] = []
    for turn in conversation.turns:
        if isinstance(turn, Message):
            input_items.append({"type": "message", "role": turn.role, "content": turn.content})
        elif isinstance(turn, ToolCall):
            input_items.append({
                "type": "function_call", "id": f"fc_{turn.id}", "call_id": f"call_{turn.id}",
                "name": turn.tool, "arguments": json.dumps(turn.arguments, separators=(",", ":")), "status": "completed",
            })
        elif isinstance(turn, ToolResult):
            input_items.append({
                "type": "function_call_output", "call_id": f"call_{turn.call_id}",
                "output": json.dumps(turn.output, separators=(",", ":")),
            })

    return {
        "input": input_items,
        "tools": [{"type": "function", "name": tool.name, "description": tool.description,
                   "parameters": tool.parameters, "strict": True} for tool in tools],
    }
