import pytest
from engine import Question, Match, TIME_LIMIT, POINTS, SPEED_BONUS


@pytest.mark.parametrize(
    "choice",
    ["B", "b", " B ", " b "]
)

def test_question_correct_answer(choice):
    question = Question(
        "What is 2 + 2?",
        ["3", "4", "5", "6"],
        "B",
    )
    assert question.is_correct(choice) 

@pytest.mark.parametrize(
    "choice",
    ["B", "b", " C ", "D", "", None]
)
@pytest.mark.slow
def test_is_wrong(choice):
    question = Question(
        "Question",
        ["3", "4", "5", "6"],
        "A"
    )
    assert question.is_correct(choice) is False


