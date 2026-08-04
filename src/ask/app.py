from collections.abc import Callable
from dataclasses import dataclass, field
from time import perf_counter

from ask.conversation import Conversation
from ask.model import Model, Proposal
from ask.openai.responses import OpenAIResponsesModel, Usage
from ask.terminal.transcript import (
    Session,
    capture,
)
from ask.terminal.transcript import (
    conversation as conversation_from_transcript,
)
from ask.tools import definitions


@dataclass(frozen=True)
class RequestMetrics:
    context_seconds: float
    model_seconds: float
    total_seconds: float
    usage: Usage | None


@dataclass
class App:
    model: Model = field(default_factory=OpenAIResponsesModel)
    last_metrics: RequestMetrics | None = field(init=False, default=None)

    def conversation(self, session: Session, request: str) -> Conversation:
        if not session.history:
            result = Conversation()
            result.user(request)
            return result

        return conversation_from_transcript(session, request, capture(session.tty))

    def request(
        self,
        session: Session,
        request: str,
        on_model_request: Callable[[], None] | None = None,
    ) -> Proposal:
        started = perf_counter()
        conversation = self.conversation(session, request)
        prepared = perf_counter()
        if on_model_request:
            on_model_request()
        proposal = self.model.propose(conversation, definitions())
        finished = perf_counter()
        self.last_metrics = RequestMetrics(
            prepared - started,
            finished - prepared,
            finished - started,
            getattr(self.model, "last_usage", None),
        )
        return proposal
