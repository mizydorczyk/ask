import unittest

from ask.app import App
from ask.conversation import Conversation, Message
from ask.model import Proposal
from ask.openai.responses import OpenAIResponsesModel
from ask.terminal.transcript import Session
from ask.tools import ToolDefinition


class RecordingModel:
    def __init__(self) -> None:
        self.conversation: Conversation | None = None
        self.tools: list[ToolDefinition] | None = None

    def propose(self, conversation: Conversation, tools: list[ToolDefinition]) -> Proposal:
        self.conversation = conversation
        self.tools = tools
        return Proposal("done", "ok")


class AppTests(unittest.TestCase):
    def test_app_uses_openai_model_by_default(self):
        self.assertIsInstance(App().model, OpenAIResponsesModel)

    def test_app_passes_neutral_conversation_and_tools_to_its_model(self):
        model = RecordingModel()
        session = Session("", "? explain", "/work", "/dev/ttys001", 0, [])

        proposal = App(model).request(session, "explain")

        self.assertEqual(proposal, Proposal("done", "ok"))
        self.assertEqual(model.conversation, Conversation([Message("user", "explain")]))
        self.assertEqual(model.tools[0].name if model.tools else None, "shell")

    def test_app_starts_progress_after_preparing_context(self):
        events = []

        class OrderedModel(RecordingModel):
            def propose(self, conversation, tools):
                events.append("model")
                return super().propose(conversation, tools)

        session = Session("", "? explain", "/work", "/dev/ttys001", 0, [])
        proposal = App(OrderedModel()).request(
            session, "explain", lambda: events.append("generating"),
        )

        self.assertEqual(proposal, Proposal("done", "ok"))
        self.assertEqual(events, ["generating", "model"])
