import copy
import os
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock

from flask import Flask, abort, flash, jsonify, redirect, render_template, request, session, url_for

from engine import Match, POINTS, Question, ROUNDS, SPEED_BONUS, TIME_LIMIT
from storage import AnswerStore, QuestionBank, ScoreBoard


def create_app(
    test_config=None, question_path=None, leaderboard_path=None, database_path=None
):
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "local-quiz-game-key-change-me"),
    )
    if test_config:
        app.config.update(test_config)

    question_bank = QuestionBank(
        question_path or Path(__file__).with_name("questions.json")
    )
    scoreboard = ScoreBoard(
        leaderboard_path or Path(__file__).with_name("leaderboard.json")
    )
    answer_store = AnswerStore(
        database_path or Path(__file__).with_name("quiz.db")
    )
    games = {}
    games_lock = RLock()
    app.extensions["quiz_games"] = games

    def current_game():
        match_code = session.get("match_code")
        player_index = session.get("player_index")
        if match_code is None or player_index not in (0, 1):
            abort(404)
        with games_lock:
            game_data = games.get(match_code)
        if game_data is None or player_index not in game_data["joined"]:
            abort(404)
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

    @app.get("/")
    def index():
        return render_template(
            "index.html",
            leaderboard=scoreboard.top(5),
            round_count=min(ROUNDS, question_bank.count()),
        )

    @app.post("/start")
    def start_game():
        player_name = request.form.get("player_name", "").strip()[:24]
        if not player_name:
            flash("Add your name to create a room.", "error")
            return redirect(url_for("index"))

        questions = question_bank.pick(ROUNDS)
        if not questions:
            flash("There are no questions available right now.", "error")
            return redirect(url_for("index"))

        match_code = secrets.token_urlsafe(9)
        game_data = {
            "match_code": match_code,
            "players": [player_name, None],
            "scores": {player_name: 0},
            "questions": [
                {"text": question.text, "options": question.options, "correct": question.correct}
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
        session.clear()
        session["match_code"] = match_code
        session["player_index"] = 0
        return redirect(url_for("game"))

    @app.route("/join/<match_code>", methods=["GET", "POST"])
    def join_game(match_code):
        with games_lock:
            game_data = games.get(match_code)
            if game_data is None:
                abort(404)
            if session.get("match_code") == match_code and session.get("player_index") == 1:
                return redirect(url_for("game"))
            if 1 in game_data["joined"]:
                abort(409, "Both player slots are already connected.")

            if request.method == "GET":
                return render_template("join.html", match_code=match_code, error=None)

            player_name = request.form.get("player_name", "").strip()[:24]
            if not player_name:
                return render_template(
                    "join.html", match_code=match_code, error="Enter your name to join."
                ), 400
            if player_name.casefold() == game_data["players"][0].casefold():
                return render_template(
                    "join.html",
                    match_code=match_code,
                    error="Choose a name different from the room creator.",
                ), 400

            session.clear()
            session["match_code"] = match_code
            session["player_index"] = 1
            game_data["players"][1] = player_name
            game_data["scores"][player_name] = 0
            game_data["joined"].append(1)
            if len(game_data["joined"]) == len(game_data["players"]):
                game_data["phase"] = "lobby"
        return redirect(url_for("game"))

    @app.post("/ready")
    def player_ready():
        match_code, _, player_index = current_game()
        with games_lock:
            game_data = games[match_code]
            if game_data["phase"] != "lobby":
                return redirect(url_for("game"))
            ready_players = game_data.setdefault("ready_players", [])
            if player_index not in ready_players:
                ready_players.append(player_index)
            if len(ready_players) == len(game_data["players"]) and len(game_data["joined"]) == len(game_data["players"]):
                game_data["phase"] = "playing"
                game_data["active_player"] = 0
                game_data["turn_started"] = time.monotonic()
        return redirect(url_for("game"))

    @app.get("/game")
    def game():
        match_code, _, player_index = current_game()
        with games_lock:
            game_data = copy.deepcopy(games[match_code])
            if game_data["phase"] == "done":
                return redirect(url_for("results"))
            question_data = game_data["questions"][game_data["round_index"]]
        return render_template(
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
            invite_url=url_for("join_game", match_code=match_code, _external=True),
        )

    @app.get("/api/state")
    def game_state():
        match_code, _, _ = current_game()
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
        return jsonify(payload)

    @app.get("/api/clock")
    def game_clock():
        match_code, _, _ = current_game()
        now = time.monotonic()
        with games_lock:
            game_data = games[match_code]
            expire_turn(game_data, now, match_code)
            remaining = None
            if game_data["phase"] == "playing":
                remaining = max(0, TIME_LIMIT - (now - game_data["turn_started"]))
            return jsonify(
                {
                    "phase": game_data["phase"],
                    "active_player": game_data["active_player"],
                    "remaining": remaining,
                }
            )

    @app.post("/answer")
    def submit_answer():
        match_code, _, player_index = current_game()
        now = time.monotonic()
        with games_lock:
            game_data = games[match_code]
            if game_data["phase"] != "playing":
                return redirect(url_for("game"))
            if player_index != game_data["active_player"]:
                flash("Wait for your turn before answering.", "error")
                return redirect(url_for("game"))

            elapsed = max(0, now - game_data["turn_started"])
            if elapsed >= TIME_LIMIT:
                expire_turn(game_data, now, match_code)
                flash("Time is up.", "error")
                return redirect(url_for("game"))

            choice = request.form.get("choice", "").strip().upper()
            if choice not in "ABCD" or len(choice) != 1:
                flash("Choose one of the four answers.", "error")
                return redirect(url_for("game"))

            game_data["answers"].append(
                create_answer(game_data, match_code, player_index, choice, elapsed)
            )
            advance_turn(game_data, now)
        return redirect(url_for("game"))

    @app.get("/api/chat")
    def chat_messages():
        match_code, _, _ = current_game()
        try:
            after_id = max(0, int(request.args.get("after", "0")))
        except ValueError:
            abort(400, "Message cursor must be an integer.")
        with games_lock:
            messages = [
                message
                for message in games[match_code]["chat"]
                if message["id"] > after_id
            ]
        return jsonify({"messages": messages})

    @app.post("/api/chat")
    def send_chat_message():
        match_code, _, player_index = current_game()
        body = request.get_json(silent=True) or {}
        text = str(body.get("message", "")).strip()[:500]
        if not text:
            return jsonify({"error": "Message cannot be empty."}), 400
        with games_lock:
            game_data = games[match_code]
            message = {
                "id": len(game_data["chat"]) + 1,
                "sender": game_data["players"][player_index],
                "text": text,
                "time": datetime.now().strftime("%H:%M"),
            }
            game_data["chat"].append(message)
        return jsonify(message), 201

    @app.post("/continue")
    def continue_game():
        match_code, _, player_index = current_game()
        with games_lock:
            game_data = games[match_code]
            if game_data["phase"] != "feedback":
                return redirect(url_for("game"))

            ready_players = game_data.setdefault("ready_players", [])
            if player_index not in ready_players:
                ready_players.append(player_index)
            if len(ready_players) < len(game_data["players"]):
                return redirect(url_for("game"))

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
                return redirect(url_for("results"))

            game_data["round_index"] += 1
            game_data["active_player"] = 0
            game_data["answers"] = []
            game_data["feedback"] = []
            game_data["ready_players"] = []
            game_data["phase"] = "playing"
            game_data["turn_started"] = time.monotonic()
        return redirect(url_for("game"))

    @app.get("/results")
    def results():
        match_code, _, _ = current_game()
        with games_lock:
            game_data = copy.deepcopy(games[match_code])
        if game_data["phase"] != "done":
            return redirect(url_for("game"))
        return render_template("results.html", game=game_data, winner=winner_for(game_data))

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")