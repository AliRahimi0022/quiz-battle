
ROUNDS = 5
TIME_LIMIT = 30
POINTS = 10
SPEED_BONUS = 3


class Question:
    def __init__(self, text, options, correct):
        self.text = text
        self.options = options
        self.correct = correct.upper()

    def is_correct(self, choice):
        if choice is None:
            return False
        return choice.strip().upper() == self.correct

    def correct_text(self):
        return self.options["ABCD".index(self.correct)]


class Match:
    def __init__(self, player1, player2, questions):
        if player1 == player2:
            raise ValueError("Unique Name per Player!")

        self.players = [player1, player2]
        self.palyers = self.players
        self.questions = questions
        self.scores = {player1: 0, player2: 0}
        self.round = 0
        self.answers = {}
        self.chat = Chat()

    def start_round(self):
        self.round += 1
        self.answers = {}
        return self.questions[self.round - 1]

    def submit(self, player, choice, elapsed):
        self.answers[player] = (choice, elapsed)

    def send_chat(self, player, message):
        if player not in self.palyers:
            raise ValueError(f"Unknown player: {player}")
        return self.chat.send(player, message)

    def resolve_round(self):
        question = self.questions[self.round - 1]

        for player in self.palyers:
            if player not in self.answers:
                continue

            choice, elapsed = self.answers[player]
            if elapsed > TIME_LIMIT:
                continue
            if question.is_correct(choice):
                bonus = SPEED_BONUS if elapsed <= TIME_LIMIT / 2 else 0
                self.scores[player] += POINTS + bonus

    def is_over(self):
        return self.round >= ROUNDS

    def winner(self):
        player1, player2 = self.palyers
        if self.scores[player1] == self.scores[player2]:
            return None

        if self.scores[player1] > self.scores[player2]:
            return player1
        return player2


class Chat:
    def __init__(self):
        self.messages = []

    def send(self, player, message):
        if player is None or str(player).strip() == "":
            raise ValueError("Player name is required")

        text = str(message).strip()
        if text == "":
            return ""

        self.messages.append((str(player), text))
        return text

    def history(self):
        return [f"{player}: {message}" for player, message in self.messages]

    def clear(self):
        self.messages.clear()
