import os
import httpx

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

def build_prompt_with_gpt(system: str, instructions: str, product_text: str, extra_wishes: str | None) -> str:
    if not OPENAI_API_KEY:
        raise RuntimeError("Missing env var: OPENAI_API_KEY")

    wishes = extra_wishes.strip() if extra_wishes else "нет"

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

    with httpx.Client(timeout=120.0) as client:
        r = client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
            json=payload,
        )
        r.raise_for_status()
        data = r.json()

    return data["choices"][0]["message"]["content"].strip()
