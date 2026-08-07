import unittest
from unittest.mock import patch

from ask.app import App
from ask.conversation import Conversation, Message, ToolCall, ToolResult
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

    def request_parameters(self, conversation: Conversation, tools: list[ToolDefinition]):
        self.conversation = conversation
        self.tools = tools
        return {"input": "snapshot"}


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

    def test_snapshot_uses_the_same_conversation_and_never_calls_propose(self):
        model = RecordingModel()
        session = Session("", "? explain", "/work", "/dev/ttys001", 0, [])

        result = App(model).snapshot(session, "explain")

        self.assertEqual(result, {"input": "snapshot"})
        self.assertEqual(model.conversation, Conversation([Message("user", "explain")]))

    def test_event_history_is_authoritative_and_records_silent_cd(self):
        model = RecordingModel()
        session = Session("", "", "/work/next", "/dev/ttys001", 0, [], events=[
            {"type": "ask", "request": "enter next", "cwd": "/work", "assistant": "Changes directory.", "command": "cd next", "call_id": "call_native_cd", "call_item_id": "fc_native_cd", "resolution": "run"},
            {"type": "shell", "command": "cd next", "cwd_before": "/work", "cwd_after": "/work/next", "exit_status": 0, "output": ""},
        ])

        App(model).request(session, "what directory am I in?")

        conversation = model.conversation
        assert conversation is not None
        self.assertEqual(conversation.turns[-1], Message("user", "what directory am I in?"))
        self.assertIn(ToolCall("call_native_cd", "shell", {"command": "cd next"}, "fc_native_cd"), conversation.turns)
        self.assertIn(ToolResult("call_native_cd", {
            "status": "completed", "executed_command": "cd next",
            "cwd_before": "/work", "cwd_after": "/work/next",
            "output": "", "exit_status": 0,
        }), conversation.turns)

    def test_cancelled_event_uses_a_linked_tool_result(self):
        model = RecordingModel()
        session = Session("", "", "/work", "/dev/ttys001", 0, [], events=[
            {"type": "ask", "request": "create", "cwd": "/work", "assistant": "Creates it.", "command": "cargo new demo", "call_id": "call_cancel", "resolution": "cancel"},
        ])

        App(model).request(session, "try another name")

        conversation = model.conversation
        assert conversation is not None
        self.assertIn(ToolCall("call_cancel", "shell", {"command": "cargo new demo"}), conversation.turns)
        self.assertIn(ToolResult("call_cancel", {
            "status": "cancelled",
            "reason": "The user cancelled the proposal; it was not executed.",
        }), conversation.turns)

    @patch("ask.app.capture")
    def test_event_context_keeps_unrelated_scrollback_commands_as_fallback(self, capture):
        capture.return_value = "prompt % git status\nclean\nprompt % ? ask"
        model = RecordingModel()
        session = Session("", "? ask", "/work", "/dev/ttys001", 0, ["git status"], events=[
            {"type": "ask", "request": "go home", "cwd": "/work", "assistant": "", "command": "cd ~", "resolution": "run"},
            {"type": "shell", "command": "cd ~", "cwd_before": "/work", "cwd_after": "/Users/me", "exit_status": 0, "output": ""},
        ])

        App(model).request(session, "ask")

        conversation = model.conversation
        assert conversation is not None
        self.assertIn(ToolCall("call_shell_1", "shell", {"command": "git status"}), conversation.turns)

    def test_snapshot_uses_the_default_model_without_an_api_key(self):
        session = Session("", "? explain", "/work", "/dev/ttys001", 0, [])

        with patch.dict("os.environ", {}, clear=True):
            result = App().snapshot(session, "explain")

        self.assertEqual(result["model"], "gpt-5.6-luna")
        self.assertEqual(result["input"][-1]["content"][0]["text"], "explain")
