import asyncio
import json

import httpx
import pytest

from coach import CoachGenerationError, generate_coach_response
from question_generation import GEMINI_ENDPOINT


def test_generate_coach_response_sends_round_context_and_reads_response():
    context = {
        "question": {
            "text": "Which option is correct?",
            "options": ["A", "B", "C", "D"],
            "correct_answer": "A",
        },
        "players": [{"name": "Ada", "answer": "A", "correct": True}],
    }

    def handle_request(request):
        assert request.url == GEMINI_ENDPOINT
        assert request.headers["x-goog-api-key"] == "test-key"
        body = json.loads(request.content)
        assert body["model"] == "test-model"
        assert "CURRENT ROUND CONTEXT:" in body["input"]
        assert json.dumps(context, ensure_ascii=False) in body["input"]
        assert "PLAYER: Ada" in body["input"]
        assert "QUESTION: How did I do?" in body["input"]
        return httpx.Response(
            200,
            json={
                "steps": [
                    {
                        "type": "model_output",
                        "content": [{"type": "text", "text": "You were correct."}],
                    }
                ]
            },
        )

    response = asyncio.run(
        generate_coach_response(
            "test-key",
            context=context,
            player_name="Ada",
            question="How did I do?",
            model="test-model",
            transport=httpx.MockTransport(handle_request),
        )
    )

    assert response == "You were correct."


def test_generate_coach_response_reports_invalid_upstream_response():
    transport = httpx.MockTransport(lambda request: httpx.Response(502))

    with pytest.raises(CoachGenerationError):
        asyncio.run(
            generate_coach_response(
                "test-key",
                context={},
                player_name="Ada",
                question="How did I do?",
                model="test-model",
                transport=transport,
            )
        )
