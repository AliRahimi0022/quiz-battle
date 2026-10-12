import math
from time import perf_counter
from app_log import AppLog
from rich.console import Console
# try:
#     from rich.console import Console
# except ModuleNotFoundError:
#     class Console:
#         def print(self, *args, **kwargs):
#             print(*args)

from engine import Match, Question, ROUNDS, TIME_LIMIT
from storage import QuestionBank, ScoreBoard

console = Console()

lquestionbank = QuestionBank()
board=ScoreBoard()
questions: list[Question] = lquestionbank.pick()

def show_leaderboard(board):
    pass
def show_menu():
    applog_get.info("Displaying main menu")
    console.print("\nQuiz Battle", style="bold cyan")
    console.print("1) New Game", style="bold green")
    console.print("2) Exit", style="bold red")


def play_round(match: Match, round_number: int):
    question = match.start_round()
    applog_get.info("Round %s started: %s", round_number, question.text)
    console.print(f"\nQuestion {round_number} of {ROUNDS}:", style="bold cyan")
    console.print(question.text, style="bold")

    for letter, option in zip("ABCD", question.options):
        console.print(f"  {letter}) {option}", style="bold")
        

    for player in match.palyers:
        start = perf_counter()
        answer = input(f"{player} answer (A-D): ").strip().upper()
        elapsed = perf_counter() - start
        match.submit(player, answer, elapsed)
        applog_get.info("%s submitted %s for round %s in %.2f seconds", player, answer, round_number, elapsed)

        if elapsed > TIME_LIMIT:
            applog_get.info("%s timed out on round %s after %.2f seconds", player, round_number, elapsed)
            console.print(f"{player}: Time is up!", style="bold red")
        elif question.is_correct(answer):
            applog_get.info("%s answered correctly on round %s in %.2f seconds", player, round_number, elapsed)
            console.print(f"{player}: Correct!", style="bold green")
        else:
            applog_get.info("%s answered incorrectly on round %s in %.2f seconds", player, round_number, elapsed)
            console.print(f"{player}: Wrong! Correct answer: {question.correct_text()}", style="bold red")

    match.resolve_round()
    applog_get.info("Round %s completed; scores: %s", round_number, match.scores)


def play():
    match = Match("Player 1", "Player 2", questions)
    applog_get.info("Starting match between %s and %s with %s questions", match.palyers[0], match.palyers[1], len(questions))

    # show_leader_board(board)
    for round_number in range(1, min(ROUNDS, len(questions)) + 1):
        play_round(match, round_number)

    console.print("\nGame over!", style="bold yellow")
    for player in match.palyers:
        console.print(f"   {player}: {match.scores[player]} points", style="bold green")

    winner = match.winner()
    if winner is None:
        console.print("   Result: Draw!", style="bold yellow")
        applog_get.info("Match finished in a draw; final scores: %s", match.scores)
    else:
        console.print(f"   Winner: {winner}", style="bold cyan")
        applog_get.info("Match finished; winner: %s; final scores: %s", winner, match.scores)

    board.record(
        winner,
        match.palyers[0], match.scores[match.palyers[0]],
        match.palyers[1], match.scores[match.palyers[1]],
    )
    applog_get.info("Match result recorded on the scoreboard")

AppLog.setup()
applog_get = AppLog.get("main")
while True:
    show_menu()
    choice = input("Your choice (1 or 2): ").strip()
    applog_get.info("User selected menu option: %s", choice)
    if choice == "1":
        applog_get.info("User started a new game")
        play()
    elif choice == "2":
        applog_get.info("User exited the application")
        console.print("Goodbye!", style="bold cyan")
        break
    else:
        applog_get.info("Rejected invalid menu option: %s", choice)
        console.print("Please enter only 1 or 2.", style="bold yellow")
