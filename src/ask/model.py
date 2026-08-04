from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from ask.conversation import Conversation
from ask.tools import ToolDefinition


@dataclass(frozen=True)
class Proposal:
    kind: Literal["done", "review"]
    comment: str
    command: str | None = None


class Model(Protocol):
    def propose(self, conversation: Conversation, tools: list[ToolDefinition]) -> Proposal: ...
