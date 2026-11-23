import tempfile
from pathlib import Path

import uvicorn

from app import create_app
from engine import Question


async def generate_test_questions(api_key, *, count, model):
    return [
        Question(
            f"Playwright test question {index + 1}",
            ["Correct answer", "Option B", "Option C", "Option D"],
            "A",
        )
        for index in range(count)
    ]


async def generate_test_coach_response(
    api_key, *, context, player_name, question, model
):
    return f"Test coach reply to: {question}"


storage_directory = tempfile.TemporaryDirectory(prefix="quiz-battle-playwright-")
storage_path = Path(storage_directory.name)
app = create_app(
    {
        "TESTING": True,
        "SECRET_KEY": "playwright-test-secret",
        "GEMINI_API_KEY": "playwright-test-key",
        "GEMINI_MODEL": "playwright-test-model",
    },
    leaderboard_path=storage_path / "leaderboard.json",
    database_path=storage_path / "answers.sqlite3",
    question_generator=generate_test_questions,
    coach_generator=generate_test_coach_response,
)


if __name__ == "__main__":
    try:
        uvicorn.run(app, host="127.0.0.1", port=5001, log_level="warning")
    finally:
        storage_directory.cleanup()
