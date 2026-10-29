from __future__ import annotations

import os
import time

import requests
from dotenv import load_dotenv


def main() -> None:
    load_dotenv()
    api_key = os.getenv("AI_GATEWAY_API_KEY")
    model = os.getenv("VERCEL_AI_MODEL", "moonshotai/kimi-k3")

    if not api_key:
        print("Missing AI_GATEWAY_API_KEY in .env")
        return

    headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
    }
    payload = {
            "model": model,
            "messages": [{"role": "user", "content": "Reply with one short sentence."}],
            "temperature": 0,
            "max_tokens": 80,
    }

    response = None
    for attempt in range(3):
        response = requests.post(
            "https://ai-gateway.vercel.sh/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=45,
        )
        if response.status_code not in {429, 500, 502, 503, 504}:
            break
        if attempt < 2:
            time.sleep(1.5 * (attempt + 1))

    print(f"Model: {model}")
    print(f"Status: {response.status_code}")
    print(response.text[:2000])


if __name__ == "__main__":
    main()
