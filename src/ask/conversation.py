from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class Message:
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True)
class ToolCall:
    id: str
    tool: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolResult:
    call_id: str
    output: dict[str, Any]


type Turn = Message | ToolCall | ToolResult


@dataclass
class Conversation:
    turns: list[Turn] = field(default_factory=list)

    def user(self, content: str) -> None:
        if content:
            self.turns.append(Message("user", content))

    def assistant(self, content: str) -> None:
        if content:
            self.turns.append(Message("assistant", content))

    def shell(
        self, sequence: int, command: str, cwd: str, output: str, status: int | None
    ) -> None:
        call_id = f"shell_{sequence}"

        self.turns.extend(
            (
                ToolCall(call_id, "shell", {"command": command, "cwd": cwd}),
                ToolResult(call_id, {"output": output, "exit_status": status}),
            )
        )
