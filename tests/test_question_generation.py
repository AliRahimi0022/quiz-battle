import asyncio
import json

import httpx
import pytest

from question_generation import (
    GEMINI_ENDPOINT,
    GEMINI_MODEL,
    QuestionGenerationError,
    generate_questions,
)


def sample_questions():
    return [
        {
            "question": f"Question {index}?",
            "options": [f"Option {letter}" for letter in "ABCD"],
            "correct": "A",
        }
        for index in range(5)
    ]


def test_generate_questions_uses_gemini_structured_output():
    payload = {"questions": sample_questions()}

    def handle_request(request):
        assert request.url == GEMINI_ENDPOINT
        assert request.headers["x-goog-api-key"] == "test-key"
        assert request.headers["Api-Revision"] == "2026-05-20"
        body = json.loads(request.content)
        assert body["model"] == GEMINI_MODEL
        assert body["response_format"]["mime_type"] == "application/json"
        assert body["response_format"]["schema"]["properties"]["questions"]
        return httpx.Response(
            200,
            json={
                "steps": [
                    {
                        "type": "model_output",
                        "content": [{"type": "text", "text": json.dumps(payload)}],
                    }
                ]
            },
        )

    questions = asyncio.run(
        generate_questions(
            "test-key", transport=httpx.MockTransport(handle_request)
        )
    )

    assert len(questions) == 5
    assert questions[0].text == "Question 0?"
    assert questions[0].correct == "A"


def test_generate_questions_rejects_wrong_question_count():
    payload = {"questions": sample_questions()[:4]}
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "steps": [
                    {
                        "type": "model_output",
                        "content": [{"type": "text", "text": json.dumps(payload)}],
                    }
                ]
            },
        )
    )

    with pytest.raises(QuestionGenerationError):
        asyncio.run(generate_questions("test-key", transport=transport))