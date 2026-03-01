import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.endpoints.ws_movies import router as ws_router
from app.db.session import get_session


async def _fake_session_dep():
    yield object()


class _FakeGraph:
    async def astream_events(self, *args, **kwargs):
        if False:
            yield {}
        raise RuntimeError("llm-secret-details")


class WsMoviesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = FastAPI()
        self.app.include_router(ws_router, prefix="/ws")
        self.app.dependency_overrides[get_session] = _fake_session_dep
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.client.close()
        self.app.dependency_overrides.clear()

    def test_invalid_payload_does_not_close_socket(self) -> None:
        with self.client.websocket_connect("/ws/movies") as ws:
            ws.send_text("not-valid-json")
            invalid_payload_resp = ws.receive_json()
            self.assertEqual(invalid_payload_resp["type"], "error")
            self.assertEqual(invalid_payload_resp["error_code"], "invalid_request")

            ws.send_json({"type": "interrupt"})
            interrupt_ack = ws.receive_json()
            self.assertEqual(interrupt_ack["type"], "interrupt_ack")

    def test_generation_error_payload_is_safe(self) -> None:
        convo = SimpleNamespace(id=1)
        user_msg = SimpleNamespace(id=2)
        fake_role = SimpleNamespace(value="user")
        fake_history_msg = SimpleNamespace(id=1, role=fake_role, content="Hello")
        fake_convo_history = [fake_history_msg]

        with patch(
            "app.crud.ws_movies.create_conversation",
            new=AsyncMock(return_value=convo),
        ), patch(
            "app.crud.ws_movies.add_message",
            new=AsyncMock(return_value=user_msg),
        ), patch(
            "app.crud.ws_movies.get_conversation_with_messages_limited",
            new=AsyncMock(return_value=fake_convo_history),
        ), patch("app.crud.ws_movies.app_graph", new=_FakeGraph()):
            with self.client.websocket_connect("/ws/movies") as ws:
                ws.send_json({"type": "start_conversation", "message": "Hi"})

                saw_error = False
                while True:
                    event = ws.receive_json()
                    if event["type"] == "error":
                        saw_error = True
                        self.assertEqual(event["error_code"], "generation_failed")
                        self.assertNotIn("llm-secret-details", json.dumps(event))
                    if event["type"] == "done":
                        break

                self.assertTrue(saw_error, "Expected a generation error event")


if __name__ == "__main__":
    unittest.main()
