from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class Message:
    role: Literal["user", "assistant", "developer"]
    content: str


@dataclass(frozen=True)
class ToolCall:
    id: str
    tool: str
    arguments: dict[str, Any]
    item_id: str | None = None


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

    def developer(self, content: str) -> None:
        if content:
            self.turns.append(Message("developer", content))

    def shell_call(
        self, call_id: str, command: str, item_id: str | None = None
    ) -> None:
        self.turns.append(ToolCall(call_id, "shell", {"command": command}, item_id))

    def tool_result(self, call_id: str, output: dict[str, Any]) -> None:
        self.turns.append(ToolResult(call_id, output))

    def shell(
        self, sequence: int, command: str, cwd: str, output: str, status: int | None
    ) -> None:
        call_id = f"call_shell_{sequence}"
        self.shell_call(call_id, command)
        self.tool_result(
            call_id,
            {
                "status": "completed",
                "executed_command": command,
                "cwd_before": cwd,
                "cwd_after": cwd,
                "output": output,
                "exit_status": status,
            },
        )
