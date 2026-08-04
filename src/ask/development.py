from ask.conversation import Conversation, Message
from ask.model import Proposal
from ask.tools import ToolDefinition


class HardcodedModel:
    def propose(self, conversation: Conversation, tools: list[ToolDefinition]) -> Proposal:
        del tools

        request = next(
            (turn.content for turn in reversed(conversation.turns)
             if isinstance(turn, Message) and turn.role == "user"),
            "",
        )

        if request.split(maxsplit=1)[:1] == ["explain"]:
            return Proposal("done", "This is a hardcoded explanation.")

        return Proposal("review", "Prints a greeting.", 'printf "Hello from ask\\n"')
