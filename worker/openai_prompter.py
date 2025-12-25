api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
print("OPENAI_KEY_PRESENT:", bool(api_key))
print("OPENAI_KEY_LEN:", len(api_key))
print("OPENAI_KEY_PREFIX:", api_key[:7])

import os
import httpx


def _req(name: str) -> str:
    v = (os.getenv(name) or "").strip()
    if not v:
        raise RuntimeError(f"Missing env var: {name}")
    return v


def build_prompt_with_gpt(system: str, instructions: str, product_text: str, extra_wishes: str | None) -> str:
    api_key = _req("OPENAI_API_KEY")

    wishes = (extra_wishes or "").strip() or "нет"

    user_msg = (
        f"{instructions}\n\n"
        f"ИНФА О ТОВАРЕ:\n{product_text}\n\n"
        f"ДОП ПОЖЕЛАНИЯ:\n{wishes}\n\n"
        "Верни ТОЛЬКО финальный prompt (без пояснений)."
    )

    payload = {
        "model": "gpt-4.1-mini",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.7,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    with httpx.Client(timeout=120.0) as client:
        r = client.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=payload,
        )
        r.raise_for_status()
        data = r.json()

    return data["choices"][0]["message"]["content"].strip()
