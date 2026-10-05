import logging

logger = logging.getLogger("log test")

def do_something():
    logger.info("doing sth...")

logging.basicConfig(filename="myapp.log",level=logging.INFO,format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger.info("started")
do_something()
logger.info("finished")

