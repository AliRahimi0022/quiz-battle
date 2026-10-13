import pytest
from engine import Question, Match, Chat, TIME_LIMIT, POINTS, SPEED_BONUS


def test_chat_records_player_messages():
    chat = Chat()

    chat.send("Alice", "hello")
    chat.send("Bob", "hi")

    assert chat.messages == [("Alice", "hello"), ("Bob", "hi")]
    assert chat.history() == ["Alice: hello", "Bob: hi"]


def test_match_contains_chat_and_tracks_messages():
    match = Match(
        "Alice",
        "Bob",
        [Question("2 + 2 = ?", ["3", "4", "5", "6"], "B")],
    )

    match.send_chat("Alice", "ready")
    match.send_chat("Bob", "let's go")

    assert match.chat.history() == ["Alice: ready", "Bob: let's go"]


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


