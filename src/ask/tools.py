from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any]


def definitions() -> list[ToolDefinition]:
    return [ToolDefinition(
        name="shell",
        description="Runs a command in the user's current shell working directory.",
        parameters={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The exact shell command to run."},
                "cwd": {"type": "string", "description": "The working directory in which to run the command."},
            },
            "required": ["command", "cwd"],
            "additionalProperties": False,
        },
    )]
