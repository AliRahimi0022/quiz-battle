from time import perf_counter

try:
    from rich.console import Console
except ModuleNotFoundError:
    class Console:
        def print(self, *args, **kwargs):
            print(*args)

from engine import Match, Question, ROUNDS, TIME_LIMIT
from storage import QuestionBank

console = Console()

lquestionbank = QuestionBank()
questions: list[Question] = lquestionbank.pick()


def show_menu():
    console.print("\nQuiz Battle", style="bold cyan")
    console.print("1) New Game", style="bold green")
    console.print("2) Exit", style="bold red")


def play_round(match: Match, round_number: int):
    question = match.start_round()
    console.print(f"\nQuestion {round_number} of {ROUNDS}:", style="bold cyan")
    console.print(question.text, style="bold")

    for letter, option in zip("ABCD", question.options):
        console.print(f"  {letter}) {option}", style="bold")

    for player in match.palyers:
        start = perf_counter()
        answer = input(f"{player} answer (A-D): ").strip().upper()
        elapsed = perf_counter() - start
        match.submit(player, answer, elapsed)

        if elapsed > TIME_LIMIT:
            console.print(f"{player}: Time is up!", style="bold red")
        elif question.is_correct(answer):
            console.print(f"{player}: Correct!", style="bold green")
        else:
            console.print(f"{player}: Wrong! Correct answer: {question.correct_text()}", style="bold red")

    match.resolve_round()


def play():
    match = Match("Player 1", "Player 2", questions)

    for round_number in range(1, min(ROUNDS, len(questions)) + 1):
        play_round(match, round_number)

    console.print("\nGame over!", style="bold yellow")
    for player in match.palyers:
        console.print(f"   {player}: {match.scores[player]} points", style="bold green")

    winner = match.winner()
    if winner is None:
        console.print("   Result: Draw!", style="bold yellow")
    else:
        console.print(f"   Winner: {winner}", style="bold cyan")


while True:
    show_menu()
    choice = input("Your choice (1 or 2): ").strip()

    if choice == "1":
        play()
    elif choice == "2":
        console.print("Goodbye!", style="bold cyan")
        break
    else:
        console.print("Please enter only 1 or 2.", style="bold yellow")