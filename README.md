# Quiz Club

A two-player quiz you run locally. One person creates a room, shares the invite link, and both players take turns answering the same questions. A correct answer is worth 10 points, with 3 extra points for answering in the first half of the 30-second turn.

## Requirements

- Python 3.10 or newer

## Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000).

| Variable | Default | Purpose |
|---|---|---|
| `HOST` | `127.0.0.1` | Bind address |
| `PORT` | `5000` | Bind port |
| `SECRET_KEY` | a local development value | Signs the session cookie. Set this before sharing the server. |
| `APP_DEBUG` | unset | Set to `1` to reload on code changes |

## Play

1. Enter a name and create a room.
2. Send the invite link to the other player. Their name must be different from yours.
3. Both players mark ready. The match starts on the host's turn.
4. Answer A–D before the clock runs out. The turn then passes to the other player.
5. After both answers, review the round and continue together.
6. When the questions run out, the results page shows the winner. Ties have no winner.

Wins and total points are kept in the hall of fame on the home page. Wins rank first, then points.

The question bank has fewer items than the configured round count, so a match uses every question in `questions.json`.

## Layout

| Path | Role |
|---|---|
| `app.py` | FastAPI routes: rooms, turns, chat, results |
| `engine.py` | Scoring rules (`Question`, `Match`, `Chat`) |
| `storage.py` | Question bank, JSON leaderboard, SQLite answer log |
| `templates/` | Home, join, game, and results pages |
| `questions.json` | Questions, four options, and the correct letter |
| `tests/` | Engine, storage, and web-flow tests |

Active rooms live in memory and disappear when the process stops. Finished matches still update `leaderboard.json`, and each answer is written to `quiz.db`. Both of those files are created on first use and are gitignored.

## Tests

```bash
pytest
```
