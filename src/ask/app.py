from collections.abc import Callable
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, cast

from ask.conversation import Conversation
from ask.errors import AskError
from ask.model import Model, Proposal
from ask.openai.responses import OpenAIResponsesModel, Usage
from ask.terminal.transcript import (
    Session,
    capture,
    conversation_from_events,
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
        if session.events:
            fallback_text = capture() if session.history else None
            result = conversation_from_events(session, request, fallback_text)
        elif not session.history:
            result = Conversation()
            result.user(request)
        else:
            result = conversation_from_transcript(session, request, capture())

        return result

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

    def snapshot(self, session: Session, request: str) -> dict[str, Any]:
        conversation = self.conversation(session, request)
        request_parameters = getattr(self.model, "request_parameters", None)

        if not callable(request_parameters):
            raise AskError("the configured model does not support OpenAI snapshots")

        payload = request_parameters(conversation, definitions())

        if not isinstance(payload, dict):
            raise AskError("the configured model returned an invalid snapshot")

        return cast(dict[str, Any], payload)
