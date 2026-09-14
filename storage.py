import json
import random
from pathlib import Path

from engine import Question, ROUNDS

QUESTION_PATH = Path(__file__).with_name("questions.json")


class QuestionBank:
    def __init__(self, path: str | Path = QUESTION_PATH) -> None:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self._questions: list[Question] = []
        for item in data:
            question: Question = Question(
                text=item["question"],
                options=item["options"],
                correct=item["correct"],
            )
            self._questions.append(question)

    def count(self) -> int:
        return len(self._questions)

    def pick(self, n: int = ROUNDS) -> list[Question]:
        if not self._questions:
            return []
        if n <= 0:
            return []
        if n >= len(self._questions):
            return list(self._questions)
        return random.sample(self._questions, k=n)