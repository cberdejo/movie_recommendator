import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.endpoints.conversations_routes import router as conversations_router
from app.db.session import get_session


async def _fake_session_dep():
    yield object()


class ConversationsApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = FastAPI()
        self.app.include_router(conversations_router, prefix="/conversations")
        self.app.dependency_overrides[get_session] = _fake_session_dep
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.client.close()
        self.app.dependency_overrides.clear()

    def test_post_conversation_serializes_expected_fields(self) -> None:
        convo = SimpleNamespace(id=17, title="Top sci-fi picks", model="litellm")
        user_msg = SimpleNamespace(id=99)

        with patch(
            "app.api.v1.endpoints.conversations_routes.create_conversation",
            new=AsyncMock(return_value=convo),
        ), patch(
            "app.api.v1.endpoints.conversations_routes.add_message",
            new=AsyncMock(return_value=user_msg),
        ):
            response = self.client.post(
                "/conversations",
                params={"use_case": "movies"},
                json={"model": "litellm", "message": "Recommend sci-fi movies"},
            )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertIn("ID", payload)
        self.assertIn("Title", payload)
        self.assertEqual(payload["ID"], 17)
        self.assertEqual(payload["Title"], "Top sci-fi picks")
        self.assertEqual(payload["model"], "litellm")


if __name__ == "__main__":
    unittest.main()
