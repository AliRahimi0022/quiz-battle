import json
import random
from engine import Question,ROUNDS

QUESTION_PATH = "questions.json"

class QuestionBank:
    def __init__(self,path:str=QUESTION_PATH)->None:
        with open(path,"r",encoding="utf-8")as f:
            data=json.load(f)
        self._questions: list[Question] =[]
        for item in data:
            question:Question=Question(
                text=item["question"],
                options=item["options"],
                correct=item["correct"]
            )
        self._questions.append(question)
    def count(self)-> int:
        return len(self._questions)
    def pick(self,n:int = ROUNDS)->list[Question]:
        return random.sample(self._questions,k=n)