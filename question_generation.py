import json

import httpx

from engine import Question, ROUNDS

GEMINI_MODEL = "gemini-3.5-flash-lite"
GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/interactions"
QUESTION_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "minItems": ROUNDS,
            "maxItems": ROUNDS,
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "options": {
                        "type": "array",
                        "minItems": 4,
                        "maxItems": 4,
                        "items": {"type": "string"},
                    },
                    "correct": {"type": "string", "enum": ["A", "B", "C", "D"]},
                },
                "required": ["question", "options", "correct"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["questions"],
    "additionalProperties": False,
}


class QuestionGenerationError(Exception):
    pass


async def generate_questions(
    api_key: str,
    *,
    count: int = ROUNDS,
    model: str = GEMINI_MODEL,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[Question]:
    if count != ROUNDS:
        raise ValueError(f"This quiz requires exactly {ROUNDS} questions.")

    request_data = {
        "model": model,
        "input": (
            f"Create exactly {count} original quiz questions in English. "
            "Cover varied general-knowledge topics, keep them concise and suitable "
            "for a friendly two-player quiz, and make each question have exactly "
            "four distinct answer options. The correct field must be the letter "
            "A, B, C, or D. Avoid ambiguous questions and do not include explanations."
        ),
        "response_format": {
            "type": "text",
            "mime_type": "application/json",
            "schema": QUESTION_SCHEMA,
        },
    }
    try:
        async with httpx.AsyncClient(timeout=20, transport=transport) as client:
            response = await client.post(
                GEMINI_ENDPOINT,
                headers={
                    "x-goog-api-key": api_key,
                    "Api-Revision": "2026-05-20",
                },
                json=request_data,
            )
            response.raise_for_status()
            response_data = response.json()
            steps = response_data.get("steps") if isinstance(response_data, dict) else None
            if not isinstance(steps, list):
                raise TypeError("Gemini response steps must be a list.")
            output_parts = []
            for step in steps:
                if not isinstance(step, dict) or step.get("type") != "model_output":
                    continue
                contents = step.get("content", [])
                if not isinstance(contents, list):
                    continue
                output_parts.extend(
                    content["text"]
                    for content in contents
                    if isinstance(content, dict)
                    and content.get("type") == "text"
                    and isinstance(content.get("text"), str)
                )
            output_text = "".join(output_parts)
            if not output_text:
                raise TypeError("Gemini response contains no text output.")
            result = json.loads(output_text)
    except (httpx.HTTPError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise QuestionGenerationError("Gemini returned an invalid response.") from error

    items = result.get("questions") if isinstance(result, dict) else None
    if not isinstance(items, list) or len(items) != count:
        raise QuestionGenerationError(f"Gemini must return exactly {count} questions.")

    questions = []
    seen_texts = set()
    for item in items:
        if not isinstance(item, dict):
            raise QuestionGenerationError("Gemini returned an invalid question.")
        text = item.get("question")
        options = item.get("options")
        correct = item.get("correct")
        if (
            not isinstance(text, str)
            or not text.strip()
            or not isinstance(options, list)
            or len(options) != 4
            or any(not isinstance(option, str) or not option.strip() for option in options)
            or len({option.strip().casefold() for option in options}) != 4
            or not isinstance(correct, str)
            or correct not in {"A", "B", "C", "D"}
            or text.strip().casefold() in seen_texts
        ):
            raise QuestionGenerationError("Gemini returned an invalid question.")
        seen_texts.add(text.strip().casefold())
        questions.append(
            Question(text.strip(), [option.strip() for option in options], correct)
        )

    return questions