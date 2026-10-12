import logging
from app_log import AppLog
import traceback

AppLog.setup("test.log")
app_log=AppLog.get("test")

while True:
    user_input = input("enter number")
    try:
        app_log.info(f"user entered {user_input}")
        if int(user_input)<18:
            raise Exception("age must be greater than 18")
        break
    except ValueError as e:
        app_log.error(f"value error {str(traceback.format_exc())}")
    except Exception as e:
        app_log.error(e)
        print("enter valid number")


