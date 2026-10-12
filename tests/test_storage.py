from storage import ScoreBoard

def test_a_new_scoreboard_is_empty(tmp_path):
    board = ScoreBoard(str(tmp_path/"leaderboard.json"))
    assert board.is_empty()

def test_an_empty_scoreboard_file_is_empty(tmp_path):
    path = tmp_path/"leaderboard.json"
    path.write_text("", encoding="utf-8")

    board = ScoreBoard(str(path))

    assert board.is_empty()
