import pytest
from markupsafe import escape

from app import create_app


def make_client(tmp_path):
    app = create_app(
        {"TESTING": True, "SECRET_KEY": "test-secret"},
        leaderboard_path=tmp_path / "leaderboard.json",
    )
    return app.test_client()


def make_lobby(tmp_path, host_name="Ada", guest_name="Lin"):
    app = create_app(
        {"TESTING": True, "SECRET_KEY": "test-secret"},
        leaderboard_path=tmp_path / "leaderboard.json",
    )
    host = app.test_client()
    guest = app.test_client()
    host.post("/start", data={"player_name": host_name})
    with host.session_transaction() as browser_session:
        match_code = browser_session["match_code"]
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
    assert b"3 questions" in home.data
    assert b'name="player_name"' in home.data
    assert b'name="player2"' not in home.data
    client.post("/start", data={"player_name": "Ada"})
    with client.session_transaction() as browser_session:
        match_code = browser_session["match_code"]

    guest = client.application.test_client()
    assert b"Your name" in guest.get(f"/join/{match_code}").data
    duplicate = guest.post(f"/join/{match_code}", data={"player_name": "ada"})

    assert duplicate.status_code == 400
    assert b"Choose a name different" in duplicate.data


def test_game_starts_only_after_both_players_are_ready(tmp_path):
    host, guest, _ = make_lobby(tmp_path)

    state = host.get("/api/state").get_json()
    assert state["phase"] == "lobby"
    assert state["joined_count"] == 2
    assert state["ready_players"] == []

    host.post("/ready")
    state = host.get("/api/state").get_json()
    assert state["phase"] == "lobby"
    assert state["ready_players"] == [0]
    assert b"Waiting for the other player" in host.get("/game").data

    guest.post("/ready")
    state = host.get("/api/state").get_json()
    assert state["phase"] == "playing"
    assert state["ready_players"] == [0, 1]
    assert b"Ada's turn" in host.get("/game").data
    assert b"Waiting for Ada" in guest.get("/game").data


def test_match_can_be_played_to_results(tmp_path):
    host, guest = make_two_players(tmp_path)
    with host.session_transaction() as browser_session:
        match_code = browser_session["match_code"]

    for round_number in range(3):
        host_page = host.get("/game").data
        guest_page = guest.get("/game").data
        game_data = host.application.extensions["quiz_games"][match_code]
        question_data = game_data["questions"][game_data["round_index"]]
        question_text = str(escape(question_data["text"])).encode()
        assert b"Ada's turn" in host_page
        assert question_text in host_page
        assert b'id="answer-form"' in host_page
        assert b"Waiting for Ada" in guest_page
        assert question_text not in guest_page
        assert b'id="answer-form"' not in guest_page

        host.post("/answer", data={"choice": "A"})
        guest_turn_page = guest.get("/game").data
        assert b"Lin's turn" in guest_turn_page
        assert question_text in guest_turn_page
        assert b'id="answer-form"' in guest_turn_page
        guest.post("/answer", data={"choice": "A"})
        assert b"Answer reveal" in host.get("/game").data

        host.post("/continue")
        state = host.get("/api/state").get_json()
        assert state["phase"] == "feedback"
        assert state["ready_players"] == [0]
        assert b"Waiting for the other player" in host.get("/game").data
        host.post("/continue")
        assert host.get("/api/state").get_json()["ready_players"] == [0]
        guest.post("/continue")
        state = host.get("/api/state").get_json()
        if round_number < 2:
            assert state["phase"] == "playing"
        else:
            assert state["phase"] == "done"

    results = host.get("/results")
    assert results.status_code == 200
    assert b"Match complete" in results.data
    assert b"Ada" in results.data
    assert b"Lin" in results.data


def test_chat_is_shared_live_between_player_sessions(tmp_path):
    host, guest = make_two_players(tmp_path)

    sent = host.post("/api/chat", json={"message": "Ready?"})
    received = guest.get("/api/chat?after=0").get_json()

    assert sent.status_code == 201
    assert received["messages"][0]["sender"] == "Ada"
    assert received["messages"][0]["text"] == "Ready?"

    guest.post("/api/chat", json={"message": "Let's play"})
    reply = host.get("/api/chat?after=1").get_json()["messages"]
    assert reply[0]["sender"] == "Lin"
    assert reply[0]["text"] == "Let's play"


def test_server_clock_tracks_elapsed_and_expires_turn(tmp_path, monkeypatch):
    now = [100.0]
    monkeypatch.setattr("app.time.monotonic", lambda: now[0])
    host, guest, _ = make_lobby(tmp_path)
    host.post("/ready")
    guest.post("/ready")

    assert host.get("/api/clock").get_json()["remaining"] == 30
    now[0] += 7.25
    assert host.get("/api/clock").get_json()["remaining"] == pytest.approx(22.75)
    host.post("/answer", data={"choice": "A"})
    assert guest.get("/api/clock").get_json()["remaining"] == 30

    now[0] += 31
    state = guest.get("/api/state").get_json()

    assert state["phase"] == "feedback"
    assert state["feedback"][0]["elapsed"] == pytest.approx(7.25)
    assert state["feedback"][1]["elapsed"] == pytest.approx(31)
    assert state["feedback"][1]["timed_out"] is True
    assert state["feedback"][1]["choice"] is None