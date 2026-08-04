from __future__ import annotations

from dataclasses import dataclass, field

from ask.conversation import Conversation
from ask.development import HardcodedModel
from ask.model import Model, Proposal
from ask.terminal.transcript import Session, capture
from ask.terminal.transcript import conversation as conversation_from_transcript
from ask.tools import definitions


@dataclass
class App:
    model: Model = field(default_factory=HardcodedModel)

    def conversation(self, session: Session, request: str) -> Conversation:
        if not session.history:
            result = Conversation()
            result.user(request)
            return result

        return conversation_from_transcript(session, request, capture(session.tty))

    def request(self, session: Session, request: str) -> Proposal:
        return self.model.propose(self.conversation(session, request), definitions())
