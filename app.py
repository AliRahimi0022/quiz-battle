import copy
import json
import os
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from engine import Match, POINTS, Question, ROUNDS, SPEED_BONUS, TIME_LIMIT
from storage import AnswerStore, QuestionBank, ScoreBoard


def create_app(
    test_config=None, question_path=None, leaderboard_path=None, database_path=None
):
    config = {
        "SECRET_KEY": os.environ.get("SECRET_KEY", "local-quiz-game-key-change-me"),
        "TESTING": False,
    }
    if test_config:
        config.update(test_config)

    app = FastAPI(title="Quiz Club")
    app.add_middleware(
        SessionMiddleware,
        secret_key=config["SECRET_KEY"],
        same_site="lax",
    )
    templates = Jinja2Templates(directory=str(Path(__file__).with_name("templates")))
    question_bank = QuestionBank(
        question_path or Path(__file__).with_name("questions.json")
    )
    scoreboard = ScoreBoard(
        leaderboard_path or Path(__file__).with_name("leaderboard.json")
    )
    answer_store = AnswerStore(database_path or Path(__file__).with_name("quiz.db"))
    games = {}
    games_lock = RLock()
    app.state.quiz_games = games

    def redirect_to(request, endpoint, **path_params):
        return RedirectResponse(
            request.url_for(endpoint, **path_params), status_code=302
        )

    def render_template(request, template_name, status_code=200, **context):
        return templates.TemplateResponse(
            request=request,
            name=template_name,
            context={
                **context,
                "messages": request.session.pop("_flashes", []),
            },
            status_code=status_code,
        )

    def flash(request, message, category="message"):
        request.session.setdefault("_flashes", []).append((category, message))

    def current_game(request):
        match_code = request.session.get("match_code")
        player_index = request.session.get("player_index")
        if match_code is None or player_index not in (0, 1):
            raise HTTPException(status_code=404)
        with games_lock:
            game_data = games.get(match_code)
        if game_data is None or player_index not in game_data["joined"]:
            raise HTTPException(status_code=404)
        return match_code, game_data, player_index

    def winner_for(game_data):
        first, second = game_data["players"]
        first_score = game_data["scores"][first]
        second_score = game_data["scores"][second]
        if first_score == second_score:
            return None
        return first if first_score > second_score else second

    def create_answer(game_data, match_code, player_index, choice, elapsed):
        question_data = game_data["questions"][game_data["round_index"]]
        question = Question(
            question_data["text"], question_data["options"], question_data["correct"]
        )
        answered_at = datetime.now(timezone.utc).isoformat()
        answer_text = (
            question.options[ord(choice) - ord("A")] if choice is not None else None
        )
        correct = question.is_correct(choice) and elapsed <= TIME_LIMIT
        score = (
            POINTS + (SPEED_BONUS if elapsed <= TIME_LIMIT / 2 else 0)
            if correct
            else 0
        )
        answer_store.record_answer(
            match_code,
            game_data["players"][player_index],
            answered_at,
            question.text,
            answer_text,
            score,
        )
        return {
            "player": game_data["players"][player_index],
            "choice": choice,
            "elapsed": elapsed,
            "answered_at": answered_at,
        }

    def resolve_round(game_data):
        question_data = game_data["questions"][game_data["round_index"]]
        question = Question(
            question_data["text"], question_data["options"], question_data["correct"]
        )
        match = Match(*game_data["players"], [question])
        match.round = 1
        match.scores = game_data["scores"].copy()
        match.answers = {
            answer["player"]: (answer["choice"], answer["elapsed"])
            for answer in game_data["answers"]
        }
        match.resolve_round()
        feedback = []
        for answer in game_data["answers"]:
            correct = (
                question.is_correct(answer["choice"])
                and answer["elapsed"] <= TIME_LIMIT
            )
            score_earned = (
                POINTS + (SPEED_BONUS if answer["elapsed"] <= TIME_LIMIT / 2 else 0)
                if correct
                else 0
            )
            choice = answer["choice"]
            feedback.append(
                {
                    **answer,
                    "correct": correct,
                    "timed_out": choice is None,
                    "answer_text": (
                        question.options[ord(choice) - ord("A")]
                        if choice is not None
                        else None
                    ),
                    "score_earned": score_earned,
                }
            )
        game_data["scores"] = match.scores
        game_data["feedback"] = feedback
        game_data["correct_text"] = question.correct_text()
        game_data["phase"] = "feedback"
        game_data["ready_players"] = []

    def advance_turn(game_data, now):
        if game_data["active_player"] == 0:
            game_data["active_player"] = 1
            game_data["turn_started"] = now
        else:
            resolve_round(game_data)

    def expire_turn(game_data, now, match_code):
        if game_data["phase"] != "playing" or game_data["turn_started"] is None:
            return
        elapsed = max(0, now - game_data["turn_started"])
        if elapsed < TIME_LIMIT:
            return
        player_index = game_data["active_player"]
        game_data["answers"].append(
            create_answer(game_data, match_code, player_index, None, elapsed)
        )
        advance_turn(game_data, now)

    def state_key(game_data):
        return ":".join(
            str(value)
            for value in (
                game_data["phase"],
                game_data["round_index"],
                game_data["active_player"],
                len(game_data["answers"]),
                len(game_data["joined"]),
                len(game_data.get("ready_players", [])),
            )
        )

    @app.get("/", name="index")
    async def index(request: Request):
        return render_template(
            request,
            "index.html",
            leaderboard=scoreboard.top(5),
            round_count=min(ROUNDS, question_bank.count()),
        )

    @app.post("/start", name="start_game")
    async def start_game(request: Request):
        form = await request.form()
        player_name = str(form.get("player_name", "")).strip()[:24]
        if not player_name:
            flash(request, "Add your name to create a room.", "error")
            return redirect_to(request, "index")

        questions = question_bank.pick(ROUNDS)
        if not questions:
            flash(request, "There are no questions available right now.", "error")
            return redirect_to(request, "index")

        match_code = secrets.token_urlsafe(9)
        game_data = {
            "match_code": match_code,
            "players": [player_name, None],
            "scores": {player_name: 0},
            "questions": [
                {
                    "text": question.text,
                    "options": question.options,
                    "correct": question.correct,
                }
                for question in questions
            ],
            "round_index": 0,
            "active_player": 0,
            "answers": [],
            "feedback": [],
            "ready_players": [],
            "chat": [],
            "joined": [0],
            "phase": "lobby",
            "turn_started": None,
            "recorded": False,
        }
        with games_lock:
            games[match_code] = game_data
        request.session.clear()
        request.session["match_code"] = match_code
        request.session["player_index"] = 0
        return redirect_to(request, "game")

    @app.api_route("/join/{match_code}", methods=["GET", "POST"], name="join_game")
    async def join_game(request: Request, match_code: str):
        form = await request.form() if request.method == "POST" else None
        with games_lock:
            game_data = games.get(match_code)
            if game_data is None:
                raise HTTPException(status_code=404)
            if (
                request.session.get("match_code") == match_code
                and request.session.get("player_index") == 1
            ):
                return redirect_to(request, "game")
            if 1 in game_data["joined"]:
                raise HTTPException(
                    status_code=409, detail="Both player slots are already connected."
                )

            if request.method == "GET":
                return render_template(
                    request, "join.html", match_code=match_code, error=None
                )

            player_name = str(form.get("player_name", "")).strip()[:24]
            if not player_name:
                return render_template(
                    request,
                    "join.html",
                    status_code=400,
                    match_code=match_code,
                    error="Enter your name to join.",
                )
            if player_name.casefold() == game_data["players"][0].casefold():
                return render_template(
                    request,
                    "join.html",
                    status_code=400,
                    match_code=match_code,
                    error="Choose a name different from the room creator.",
                )

            request.session.clear()
            request.session["match_code"] = match_code
            request.session["player_index"] = 1
            game_data["players"][1] = player_name
            game_data["scores"][player_name] = 0
            game_data["joined"].append(1)
            if len(game_data["joined"]) == len(game_data["players"]):
                game_data["phase"] = "lobby"
        return redirect_to(request, "game")

    @app.post("/ready", name="player_ready")
    async def player_ready(request: Request):
        match_code, _, player_index = current_game(request)
        with games_lock:
            game_data = games[match_code]
            if game_data["phase"] != "lobby":
                return redirect_to(request, "game")
            ready_players = game_data.setdefault("ready_players", [])
            if player_index not in ready_players:
                ready_players.append(player_index)
            if (
                len(ready_players) == len(game_data["players"])
                and len(game_data["joined"]) == len(game_data["players"])
            ):
                game_data["phase"] = "playing"
                game_data["active_player"] = 0
                game_data["turn_started"] = time.monotonic()
        return redirect_to(request, "game")

    @app.get("/game", name="game")
    async def game(request: Request):
        match_code, _, player_index = current_game(request)
        with games_lock:
            game_data = copy.deepcopy(games[match_code])
            if game_data["phase"] == "done":
                return redirect_to(request, "results")
            question_data = game_data["questions"][game_data["round_index"]]
        return render_template(
            request,
            "game.html",
            game=game_data,
            question=question_data,
            player_index=player_index,
            your_turn=(
                game_data["phase"] == "playing"
                and game_data["active_player"] == player_index
            ),
            round_number=game_data["round_index"] + 1,
            total_rounds=len(game_data["questions"]),
            time_limit=TIME_LIMIT,
            state_key=state_key(game_data),
            player_ready=player_index in game_data.get("ready_players", []),
            ready_count=len(game_data.get("ready_players", [])),
            joined_count=len(game_data["joined"]),
            invite_url=str(request.url_for("join_game", match_code=match_code)),
        )

    @app.get("/api/state", name="game_state")
    async def game_state(request: Request):
        match_code, _, _ = current_game(request)
        with games_lock:
            game_data = games[match_code]
            expire_turn(game_data, time.monotonic(), match_code)
            payload = {
                "key": state_key(game_data),
                "phase": game_data["phase"],
                "round_index": game_data["round_index"],
                "active_player": game_data["active_player"],
                "answer_count": len(game_data["answers"]),
                "joined_count": len(game_data["joined"]),
                "scores": game_data["scores"],
                "ready_players": game_data.get("ready_players", []),
            }
            if game_data["phase"] == "feedback":
                payload["feedback"] = game_data["feedback"]
        return JSONResponse(payload)

    @app.get("/api/clock", name="game_clock")
    async def game_clock(request: Request):
        match_code, _, _ = current_game(request)
        now = time.monotonic()
        with games_lock:
            game_data = games[match_code]
            expire_turn(game_data, now, match_code)
            remaining = None
            if game_data["phase"] == "playing":
                remaining = max(0, TIME_LIMIT - (now - game_data["turn_started"]))
            return JSONResponse(
                {
                    "phase": game_data["phase"],
                    "active_player": game_data["active_player"],
                    "remaining": remaining,
                }
            )

    @app.post("/answer", name="submit_answer")
    async def submit_answer(request: Request):
        match_code, _, player_index = current_game(request)
        now = time.monotonic()
        form = await request.form()
        with games_lock:
            game_data = games[match_code]
            if game_data["phase"] != "playing":
                return redirect_to(request, "game")
            if player_index != game_data["active_player"]:
                flash(request, "Wait for your turn before answering.", "error")
                return redirect_to(request, "game")

            elapsed = max(0, now - game_data["turn_started"])
            if elapsed >= TIME_LIMIT:
                expire_turn(game_data, now, match_code)
                flash(request, "Time is up.", "error")
                return redirect_to(request, "game")

            choice = str(form.get("choice", "")).strip().upper()
            if choice not in "ABCD" or len(choice) != 1:
                flash(request, "Choose one of the four answers.", "error")
                return redirect_to(request, "game")

            game_data["answers"].append(
                create_answer(game_data, match_code, player_index, choice, elapsed)
            )
            advance_turn(game_data, now)
        return redirect_to(request, "game")

    @app.get("/api/chat", name="chat_messages")
    async def chat_messages(request: Request):
        match_code, _, _ = current_game(request)
        try:
            after_id = max(0, int(request.query_params.get("after", "0")))
        except ValueError as error:
            raise HTTPException(
                status_code=400, detail="Message cursor must be an integer."
            ) from error
        with games_lock:
            messages = [
                message
                for message in games[match_code]["chat"]
                if message["id"] > after_id
            ]
        return JSONResponse({"messages": messages})

    @app.post("/api/chat", name="send_chat_message")
    async def send_chat_message(request: Request):
        match_code, _, player_index = current_game(request)
        try:
            body = await request.json()
        except json.JSONDecodeError:
            body = {}
        if not isinstance(body, dict):
            body = {}
        text = str(body.get("message", "")).strip()[:500]
        if not text:
            return JSONResponse({"error": "Message cannot be empty."}, status_code=400)
        with games_lock:
            game_data = games[match_code]
            message = {
                "id": len(game_data["chat"]) + 1,
                "sender": game_data["players"][player_index],
                "text": text,
                "time": datetime.now().strftime("%H:%M"),
            }
            game_data["chat"].append(message)
        return JSONResponse(message, status_code=201)

    @app.post("/continue", name="continue_game")
    async def continue_game(request: Request):
        match_code, _, player_index = current_game(request)
        with games_lock:
            game_data = games[match_code]
            if game_data["phase"] != "feedback":
                return redirect_to(request, "game")

            ready_players = game_data.setdefault("ready_players", [])
            if player_index not in ready_players:
                ready_players.append(player_index)
            if len(ready_players) < len(game_data["players"]):
                return redirect_to(request, "game")

            if game_data["round_index"] + 1 >= len(game_data["questions"]):
                game_data["phase"] = "done"
                if not game_data["recorded"]:
                    scoreboard.record(
                        winner_for(game_data),
                        game_data["players"][0],
                        game_data["scores"][game_data["players"][0]],
                        game_data["players"][1],
                        game_data["scores"][game_data["players"][1]],
                    )
                    game_data["recorded"] = True
                return redirect_to(request, "results")

            game_data["round_index"] += 1
            game_data["active_player"] = 0
            game_data["answers"] = []
            game_data["feedback"] = []
            game_data["ready_players"] = []
            game_data["phase"] = "playing"
            game_data["turn_started"] = time.monotonic()
        return redirect_to(request, "game")

    @app.get("/results", name="results")
    async def results(request: Request):
        match_code, _, _ = current_game(request)
        with games_lock:
            game_data = copy.deepcopy(games[match_code])
        if game_data["phase"] != "done":
            return redirect_to(request, "game")
        return render_template(
            request, "results.html", game=game_data, winner=winner_for(game_data)
        )

    return app


app = create_app()


if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "5000")),
        reload=os.environ.get("APP_DEBUG") == "1",
    )
