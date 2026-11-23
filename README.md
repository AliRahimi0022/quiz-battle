# Quiz Club

[فارسی](READMEFA.md)

A two-player quiz you run locally. One person creates a room, shares the invite link, and both players take turns answering the same questions. A correct answer is worth 10 points, with 3 extra points for answering in the first half of the 30-second turn.

## Requirements

- Python 3.10 or newer

## Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Add your Gemini API key to a `.env` file in the project root:

```env
GEMINI_API_KEY=your-google-ai-studio-key
```

Then start the app:

```bash
python app.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000).

| Variable | Default | Purpose |
|---|---|---|
| `HOST` | `127.0.0.1` | Bind address |
| `PORT` | `5000` | Bind port |
| `SECRET_KEY` | a local development value | Signs the session cookie. Set this before sharing the server. |
| `GEMINI_API_KEY` | unset | Optional Google Gemini API key, loaded from the environment or project `.env` file. When set, each new room gets five generated questions and the round coach can answer questions; otherwise the local question bank is used and the coach is unavailable. |
| `GEMINI_MODEL` | `gemini-3.5-flash-lite` | Gemini model used to generate questions and coach replies |
| `APP_DEBUG` | unset | Set to `1` to reload on code changes |

## Play

1. Enter a name and create a room.
2. Send the invite link to the other player. Their name must be different from yours.
3. Both players mark ready. The match starts on the host's turn.
4. Answer A–D before the clock runs out. The turn then passes to the other player.
5. After both answers, review the round, ask the coach about your answer or score, and continue together.
6. When the questions run out, the results page shows the winner. Ties have no winner.

Wins and total points are kept in the hall of fame on the home page. Wins rank first, then points.

With `GEMINI_API_KEY` configured, each new room requests five fresh English questions from Gemini. If the key is missing or the API request fails, the five local questions in `questions.json` are used instead.

After both players answer, the coach first asks for the signed-in player's name. It can then answer questions using only the current question, its answer choices and correct answer, both players' answers, and their scores. It does not receive future questions, chat history, or database records. Coach replies require `GEMINI_API_KEY`.

## Agent demo

Run the Gemini agent demo, which can report the current local time or roll a six-sided die:

Set these values in a `.env` file in the project root:

```env
GEMINI_API_KEY=your-google-ai-studio-key
# GEMINI_MODEL=gemini-3.5-flash-lite
```

Then run:

```bash
python agent_demo.py
```

Enter a prompt such as “Tell me the current time and roll a die.” The model uses the two local tools to complete the request.
Each tool invocation and its result are printed in the terminal and saved to `agent_demo.log`.

## Layout

| Path | Role |
|---|---|
| `app.py` | FastAPI routes: rooms, turns, chat, results |
| `coach.py` | Gemini responses grounded in current-round quiz context |
| `agent_demo.py` | Gemini agent demo with current-time and dice tools |
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

## Browser tests

With the Python environment set up, install the Node.js dependencies and Chromium, then run the Playwright end-to-end test:

```bash
npm ci
npx playwright install chromium
npm run test:e2e
```

The test uses temporary storage and mock question and coach generators, so it does not need a Gemini API key or modify the app's local data.
