import asyncio
import logging
import os
import random
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

from question_generation import GEMINI_MODEL

GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models"
MAX_TOOL_ROUNDS = 5
LOGGER = logging.getLogger(__name__)

TOOLS = [
    {
        "function_declarations": [
            {
                "name": "get_current_time",
                "description": "نمایش زمان و تاریخ جاری به وقت محلی سیستم.",
                "parameters": {"type": "OBJECT", "properties": {}},
            },
            {
                "name": "roll_dice",
                "description": "انداختن یک تاس معمولی شش‌وجهی.",
                "parameters": {"type": "OBJECT", "properties": {}},
            },
        ]
    }
]


def get_current_time() -> dict[str, str]:
    return {"current_time": datetime.now().astimezone().isoformat(timespec="seconds")}


def roll_dice() -> dict[str, int]:
    return {"result": random.randint(1, 6), "sides": 6}


TOOL_FUNCTIONS: dict[str, Callable[[], dict[str, str | int]]] = {
    "get_current_time": get_current_time,
    "roll_dice": roll_dice,
}


def _run_tool(name: str, arguments: Any) -> dict[str, str | int]:
    if name not in TOOL_FUNCTIONS:
        raise ValueError(f"مدل ابزار ناشناخته‌ای را درخواست کرد: {name}")
    if not isinstance(arguments, dict) or arguments:
        raise ValueError(f"آرگومان‌های ابزار {name} معتبر نیستند.")
    return TOOL_FUNCTIONS[name]()


async def run_agent(
    prompt: str,
    api_key: str,
    *,
    model: str = GEMINI_MODEL,
    transport: httpx.AsyncBaseTransport | None = None,
) -> str:
    if not prompt.strip():
        raise ValueError("درخواست نمی‌تواند خالی باشد.")
    if not api_key:
        raise ValueError("کلید API نمی‌تواند خالی باشد.")
    if not model:
        raise ValueError("نام مدل نمی‌تواند خالی باشد.")

    contents: list[dict[str, Any]] = [
        {"role": "user", "parts": [{"text": prompt}]}
    ]
    request_url = f"{GEMINI_ENDPOINT}/{model}:generateContent"

    async with httpx.AsyncClient(timeout=30, transport=transport) as client:
        for _ in range(MAX_TOOL_ROUNDS):
            response = await client.post(
                request_url,
                headers={"x-goog-api-key": api_key},
                json={"contents": contents, "tools": TOOLS},
            )
            response.raise_for_status()
            response_data = response.json()

            if not isinstance(response_data, dict):
                raise RuntimeError("پاسخ جمینای در قالب معتبری نیست.")
            candidates = response_data.get("candidates")
            if not isinstance(candidates, list) or not candidates:
                raise RuntimeError("پاسخ جمینای شامل candidate معتبری نیست.")
            candidate = candidates[0]
            if not isinstance(candidate, dict):
                raise RuntimeError("candidate جمینای در قالب معتبری نیست.")
            content = candidate.get("content")
            parts = content.get("parts") if isinstance(content, dict) else None
            if not isinstance(parts, list):
                raise RuntimeError("پاسخ جمینای شامل بخش‌های معتبری نیست.")

            function_calls = [
                part["functionCall"]
                for part in parts
                if isinstance(part, dict) and isinstance(part.get("functionCall"), dict)
            ]
            if not function_calls:
                text = "".join(
                    part["text"]
                    for part in parts
                    if isinstance(part, dict) and isinstance(part.get("text"), str)
                )
                if not text:
                    raise RuntimeError("جمینای پاسخ متنی برنگرداند.")
                return text

            contents.append(content)
            function_responses = []
            for function_call in function_calls:
                name = function_call.get("name")
                arguments = function_call.get("args", {})
                if not isinstance(name, str):
                    raise RuntimeError("نام ابزار در پاسخ جمینای معتبر نیست.")
                LOGGER.info("در حال اجرای ابزار: %s", name)
                tool_result = _run_tool(name, arguments)
                LOGGER.info("نتیجه ابزار %s: %s", name, tool_result)
                function_responses.append(
                    {
                        "functionResponse": {
                            "name": name,
                            "response": tool_result,
                        }
                    }
                )
            contents.append({"role": "user", "parts": function_responses})

    raise RuntimeError("تعداد فراخوانی ابزارها از حد مجاز بیشتر شد.")


def main() -> None:
    load_dotenv(Path(__file__).with_name(".env"))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(
                Path(__file__).with_name("agent_demo.log"), encoding="utf-8"
            ),
        ],
    )
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise SystemExit("مقدار GEMINI_API_KEY را در فایل .env تنظیم کنید.")

    prompt = input("از agent چه می‌خواهید؟ ")
    model = os.getenv("GEMINI_MODEL", GEMINI_MODEL)
    answer = asyncio.run(run_agent(prompt, api_key, model=model))
    print(answer)


if __name__ == "__main__":
    main()