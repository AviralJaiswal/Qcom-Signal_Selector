import unittest
from unittest.mock import patch, MagicMock

from app.assistant.service import (
    handle_message,
    initialize_session,
    _is_order_intent_trigger,
)
from app.chat.session import session_store


class AssistantServiceTests(unittest.TestCase):
    def setUp(self):
        session_store._data.clear()

    @patch("app.assistant.service.generate_dynamic_greeting", return_value="Dynamic Welcome!")
    def test_session_welcome_dynamic_greeting(self, mock_greeting):
        result = initialize_session("test-welcome")
        self.assertEqual(result["response"], "Dynamic Welcome!")
        self.assertEqual(result["mode"], "RAG")
        self.assertTrue(result["conversationId"].startswith("CONV-"))
        self.assertIsNotNone(session_store.get("test-welcome"))

    @patch("app.assistant.service.generate", return_value="Custom existing welcome.")
    def test_existing_profile_welcome(self, mock_gen):
        result = initialize_session("existing-session", profile="existing")
        self.assertEqual(result["response"], "Custom existing welcome.")
        self.assertEqual(result["mode"], "ORDER_FLOW")

    def test_order_intent_trigger(self):
        self.assertTrue(_is_order_intent_trigger("600013"))
        self.assertTrue(_is_order_intent_trigger("I want a new fiber connection"))
        self.assertFalse(_is_order_intent_trigger("What is fiber broadband?"))

    @patch("app.assistant.service.query_faq_collection", return_value=["Fiber is optical connection."])
    @patch("app.assistant.service.generate_grounded_faq_answer", return_value="Fiber broadband is optical cable internet.")
    def test_knowledge_message_routes_to_rag(self, mock_answer, mock_query):
        initialize_session("rag-session")
        result = handle_message("rag-session", "What is fiber broadband?", db=MagicMock())
        self.assertEqual(result["mode"], "RAG")
        self.assertIn("Fiber", result["response"])

    @patch("app.assistant.service.qualify", return_value={"serviceable": True, "requires_full_address": True, "address_qualified": False, "city": "Chennai", "state": "Tamil Nadu"})
    def test_pincode_routes_to_order_flow(self, mock_qualify):
        initialize_session("order-session")
        result = handle_message("order-session", "600013", db=MagicMock())
        self.assertEqual(result["mode"], "ORDER_FLOW")
        self.assertEqual(session_store.get("order-session")["mode"], "ORDER_FLOW")

    @patch("app.assistant.service.qualify", return_value={"serviceable": True, "requires_full_address": True, "address_qualified": False, "city": "Chennai", "state": "Tamil Nadu"})
    def test_one_way_state_machine_guardrail(self, mock_qualify):
        """Once in ORDER_FLOW, session cannot revert to RAG."""
        initialize_session("locked-session")
        handle_message("locked-session", "600013", db=MagicMock())
        # Subsequent query asking a question stays in ORDER_FLOW
        result = handle_message("locked-session", "What is Wi-Fi 6?", db=MagicMock())
        self.assertEqual(result["mode"], "ORDER_FLOW")


if __name__ == "__main__":
    unittest.main()

