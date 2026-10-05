import logging

class AppLog:
    @staticmethod
    def setup(filename="quiz_game.log"):
        logging.basicConfig(
            filename=filename,
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s"
        )
    @staticmethod 
    def get(name):
        return logging.getLogger(name)