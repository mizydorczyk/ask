from dataclasses import dataclass
from typing import Literal, Protocol

from ask.conversation import Conversation
from ask.tools import ToolDefinition


@dataclass(frozen=True)
class Proposal:
    kind: Literal["done", "review"]
    comment: str
    command: str | None = None
    call_id: str | None = None
    call_item_id: str | None = None


class Model(Protocol):
    def propose(self, conversation: Conversation, tools: list[ToolDefinition]) -> Proposal: ...
