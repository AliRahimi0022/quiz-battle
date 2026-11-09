from datetime import datetime
import sqlite3
from fastapi.testclient import TestClient

import pytest
from markupsafe import escape

from app import create_app
from engine import Question as QuestionData
from question_generation import QuestionGenerationError


def make_client(tmp_path):
    app = create_app(
        {"TESTING": True, "SECRET_KEY": "test-secret", "GEMINI_API_KEY": ""},
        leaderboard_path=tmp_path / "leaderboard.json",
        database_path=tmp_path / "answers.sqlite3",
    )
    return TestClient(app, follow_redirects=False)


def make_lobby(tmp_path, host_name="Ada", guest_name="Lin"):
    app = create_app(
        {"TESTING": True, "SECRET_KEY": "test-secret", "GEMINI_API_KEY": ""},
        leaderboard_path=tmp_path / "leaderboard.json",
        database_path=tmp_path / "answers.sqlite3",
    )
    host = TestClient(app, follow_redirects=False)
    guest = TestClient(app, follow_redirects=False)
    host.post("/start", data={"player_name": host_name})
    match_code = next(iter(app.state.quiz_games))
    guest.get(f"/join/{match_code}")
    guest.post(f"/join/{match_code}", data={"player_name": guest_name})
    return host, guest, match_code


def make_two_players(tmp_path):
    host, guest, _ = make_lobby(tmp_path)
    host.post("/ready")
    guest.post("/ready")
    return host, guest


def test_home_page_and_duplicate_names(tmp_path):
    client = make_client(tmp_path)

    home = client.get("/")
    assert home.status_code == 200
    assert b"5 questions" in home.content
    assert b'name="player_name"' in home.content
    assert b'name="player2"' not in home.content
    invalid_start = client.post("/start", data={"player_name": " "})
    assert invalid_start.status_code == 302
    assert b"Add your name to create a room" in client.get("/").content
    client.post("/start", data={"player_name": "Ada"})
    match_code = next(iter(client.app.state.quiz_games))

    guest = TestClient(client.app, follow_redirects=False)
    assert b"Your name" in guest.get(f"/join/{match_code}").content
    duplicate = guest.post(f"/join/{match_code}", data={"player_name": "ada"})

    assert duplicate.status_code == 400
    assert b"Choose a name different" in duplicate.content


def test_new_room_uses_gemini_generated_questions(tmp_path):
    generated = [
        QuestionData("Generated question", ["One", "Two", "Three", "Four"], "A")
        for _ in range(5)
    ]
    calls = []

    async def generate(api_key, *, count, model):
        calls.append((api_key, count, model))
        return generated

    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "GEMINI_API_KEY": "test-gemini-key",
            "GEMINI_MODEL": "gemini-test-model",
        },
        leaderboard_path=tmp_path / "leaderboard.json",
        database_path=tmp_path / "answers.sqlite3",
        question_generator=generate,
    )
    client = TestClient(app, follow_redirects=False)

    response = client.post("/start", data={"player_name": "Ada"})

    assert response.status_code == 302
    match_code = next(iter(app.state.quiz_games))
    questions = app.state.quiz_games[match_code]["questions"]
    assert len(questions) == 5
    assert all(question["text"] == "Generated question" for question in questions)
    assert calls == [("test-gemini-key", 5, "gemini-test-model")]


def test_new_room_falls_back_to_local_questions_when_gemini_fails(tmp_path):
    async def fail_generation(api_key, *, count, model):
        raise QuestionGenerationError("test failure")

    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "GEMINI_API_KEY": "test-gemini-key",
        },
        leaderboard_path=tmp_path / "leaderboard.json",
        database_path=tmp_path / "answers.sqlite3",
        question_generator=fail_generation,
    )
    client = TestClient(app, follow_redirects=False)

    response = client.post("/start", data={"player_name": "Ada"})

    assert response.status_code == 302
    match_code = next(iter(app.state.quiz_games))
    assert len(app.state.quiz_games[match_code]["questions"]) == 5


def test_game_starts_only_after_both_players_are_ready(tmp_path):
    host, guest, _ = make_lobby(tmp_path)

    state = host.get("/api/state").json()
    assert state["phase"] == "lobby"
    assert state["joined_count"] == 2
    assert state["ready_players"] == []

    host.post("/ready")
    state = host.get("/api/state").json()
    assert state["phase"] == "lobby"
    assert state["ready_players"] == [0]
    assert b"Waiting for the other player" in host.get("/game").content

    guest.post("/ready")
    state = host.get("/api/state").json()
    assert state["phase"] == "playing"
    assert state["ready_players"] == [0, 1]
    assert b"Ada's turn" in host.get("/game").content
    assert b"Waiting for Ada" in guest.get("/game").content


def test_match_can_be_played_to_results(tmp_path):
    host, guest = make_two_players(tmp_path)
    match_code = next(iter(host.app.state.quiz_games))

    for round_number in range(5):
        host_page = host.get("/game").content
        guest_page = guest.get("/game").content
        game_data = host.app.state.quiz_games[match_code]
        question_data = game_data["questions"][game_data["round_index"]]
        question_text = str(escape(question_data["text"])).encode()
        assert b"Ada's turn" in host_page
        assert question_text in host_page
        assert b'id="answer-form"' in host_page
        assert b"Waiting for Ada" in guest_page
        assert question_text not in guest_page
        assert b'id="answer-form"' not in guest_page

        host.post("/answer", data={"choice": "A"})
        guest_turn_page = guest.get("/game").content
        assert b"Lin's turn" in guest_turn_page
        assert question_text in guest_turn_page
        assert b'id="answer-form"' in guest_turn_page
        guest.post("/answer", data={"choice": "A"})
        assert b"Answer reveal" in host.get("/game").content

        host.post("/continue")
        state = host.get("/api/state").json()
        assert state["phase"] == "feedback"
        assert state["ready_players"] == [0]
        assert b"Waiting for the other player" in host.get("/game").content
        host.post("/continue")
        assert host.get("/api/state").json()["ready_players"] == [0]
        guest.post("/continue")
        state = host.get("/api/state").json()
        if round_number < 4:
            assert state["phase"] == "playing"
        else:
            assert state["phase"] == "done"

    results = host.get("/results")
    assert results.status_code == 200
    assert b"Match complete" in results.content
    assert b"Ada" in results.content
    assert b"Lin" in results.content


def test_chat_is_shared_live_between_player_sessions(tmp_path):
    host, guest = make_two_players(tmp_path)

    sent = host.post("/api/chat", json={"message": "Ready?"})
    received = guest.get("/api/chat?after=0").json()

    assert sent.status_code == 201
    assert received["messages"][0]["sender"] == "Ada"
    assert received["messages"][0]["text"] == "Ready?"

    guest.post("/api/chat", json={"message": "Let's play"})
    reply = host.get("/api/chat?after=1").json()["messages"]
    assert reply[0]["sender"] == "Lin"
    assert reply[0]["text"] == "Let's play"


def test_server_clock_tracks_elapsed_and_expires_turn(tmp_path, monkeypatch):
    now = [100.0]
    monkeypatch.setattr("app.time.monotonic", lambda: now[0])
    host, guest, _ = make_lobby(tmp_path)
    host.post("/ready")
    guest.post("/ready")

    assert host.get("/api/clock").json()["remaining"] == 30
    now[0] += 7.25
    assert host.get("/api/clock").json()["remaining"] == pytest.approx(22.75)
    host.post("/answer", data={"choice": "A"})
    assert guest.get("/api/clock").json()["remaining"] == 30

    now[0] += 31
    guest.post("/answer", data={"choice": "A"})
    state = guest.get("/api/state").json()

    assert state["phase"] == "feedback"
    assert state["feedback"][0]["elapsed"] == pytest.approx(7.25)
    assert state["feedback"][1]["elapsed"] == pytest.approx(31)
    assert state["feedback"][1]["timed_out"] is True
    assert state["feedback"][1]["choice"] is None
    with sqlite3.connect(tmp_path / "answers.sqlite3") as connection:
        timeout_answer = connection.execute(
            "SELECT player, answer, score FROM answers WHERE player = 'Lin'"
        ).fetchone()
    assert timeout_answer == ("Lin", None, 0)


def test_answers_are_persisted_with_player_time_question_answer_and_score(
    tmp_path, monkeypatch
):
    now = [100.0]
    monkeypatch.setattr("app.time.monotonic", lambda: now[0])
    host, guest = make_two_players(tmp_path)
    match_code = next(iter(host.app.state.quiz_games))
    game_data = host.app.state.quiz_games[match_code]
    question = game_data["questions"][0]
    correct_choice = question["correct"]
    wrong_choice = "A" if correct_choice != "A" else "B"

    host.post("/answer", data={"choice": correct_choice})
    guest.post("/answer", data={"choice": wrong_choice})

    feedback = host.get("/api/state").json()["feedback"]
    assert feedback[0]["score_earned"] == 13
    assert feedback[1]["score_earned"] == 0
    reveal = host.get("/game").content
    assert b"answer-correct" in reveal
    assert b"correct-answer-badge" in reveal

    with sqlite3.connect(tmp_path / "answers.sqlite3") as connection:
        rows = connection.execute(
            """
            SELECT match_code, player, answered_at, question, answer, score
            FROM answers ORDER BY id
            """
        ).fetchall()

    assert [row[0] for row in rows] == [match_code, match_code]
    assert [row[1] for row in rows] == ["Ada", "Lin"]
    assert [row[3] for row in rows] == [question["text"], question["text"]]
    assert [row[4] for row in rows] == [
        question["options"][ord(correct_choice) - ord("A")],
        question["options"][ord(wrong_choice) - ord("A")],
    ]
    assert [row[5] for row in rows] == [13, 0]
    assert all(datetime.fromisoformat(row[2]).utcoffset() is not None for row in rows)