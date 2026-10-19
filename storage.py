import json
import random
from pathlib import Path
# from app_log import AppLog
from engine import Question, ROUNDS
# AppLog.setup()
QUESTION_PATH = Path(__file__).with_name("questions.json")
QUESTION_PATH = "questions.json"
LEADERBOARD_PATH = "leaderboard.json"
# uiyuykytj
class QuestionBank:
    def __init__(self, path: str | Path = QUESTION_PATH) -> None:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            pass
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


class ScoreBoard:
    def __init__(self,path:str = LEADERBOARD_PATH) -> None:
        self._path = Path(path)
        self._data:dict[str,dict[str,int]] = {}

        if self._path.exists():
            with open(self._path, encoding="utf-8") as f:
                contents = f.read()
            if contents.strip():
                self._data = json.loads(contents)
    def is_empty(self) -> bool:
        return not self._data
    def record(self,winner:str,player1,score1,player2,score2) -> None:
        for name,points in [(player1,score1),(player2,score2)]:
            if name not in self._data:
                self._data[name] = {"wins":0,"points":0}
            self._data[name]["points"] += points

        if winner is not None:
            self._data[winner]["wins"] += 1
        self._save()
    def top(self,n:int = 5) -> list[tuple[str,int]]:
        def wins_then_points(item) -> tuple:
            return item[1]["wins"], item[1]["points"]
        return sorted(self._data.items(),key=wins_then_points,reverse=True)[:n]
    def _save(self) -> None:
        with open(self._path,"w",encoding="utf-8")as f:
            json.dump(self._data,f,ensure_ascii=False,indent=2)
