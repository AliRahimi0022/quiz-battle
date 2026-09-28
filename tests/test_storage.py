from storage import ScoreBoard

def test_a_new_scoreboard_is_empty(tmp_path):
    board = ScoreBoard(str(tmp_path/"leaderboard.json"))
    assert board.is_empty()

