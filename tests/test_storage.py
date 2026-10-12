from storage import ScoreBoard

def test_a_new_scoreboard_is_empty(tmp_path):
    board = ScoreBoard(str(tmp_path/"leaderboard.json"))
    assert board.is_empty()

def test_an_empty_scoreboard_file_is_empty(tmp_path):
    path = tmp_path/"leaderboard.json"
    path.write_text("", encoding="utf-8")

    board = ScoreBoard(str(path))

    assert board.is_empty()

def test_record_saves_wins_and_points(tmp_path):
    path = tmp_path/"leaderboard.json"
    board = ScoreBoard(str(path))

    board.record("Player 1", "Player 1", 13, "Player 2", 10)

    assert ScoreBoard(str(path)).top() == [
        ("Player 1", {"wins": 1, "points": 13}),
        ("Player 2", {"wins": 0, "points": 10}),
    ]
