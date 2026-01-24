import os
import time
import httpx
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def _req(name: str) -> str:
    v = (os.getenv(name) or "").strip()
    if not v:
        raise RuntimeError(f"Missing env var: {name}")
    return v


def load_proxies_from_file(filepath: str) -> list:
    """Загрузить прокси из файла."""
    try:
        if not os.path.exists(filepath):
            return []
        with open(filepath, 'r') as f:
            return [line.strip() for line in f if line.strip() and not line.startswith('#')]
    except Exception as e:
        logger.error(f"Failed to load proxies: {e}")
        return []


def get_proxy_for_openai() -> Optional[dict]:
    """
    Получить прокси для OpenAI запроса.
    
    Returns:
        Dict с настройками прокси для httpx или None
    """
    proxy_file = os.getenv("PROXY_FILE", "/app/proxies.txt")
    proxies = load_proxies_from_file(proxy_file)
    
    if not proxies:
        return None
    
    # Берем первый рабочий прокси (можно добавить ротацию позже)
    proxy = proxies[0]
    parts = proxy.split(":")
    
    if len(parts) == 4:
        ip, port, user, password = parts
        proxy_url = f"http://{user}:{password}@{ip}:{port}"
        logger.debug(f"🔄 Using proxy for OpenAI: {ip}:{port}")
        return {"http://": proxy_url, "https://": proxy_url}
    
    return None


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
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.7,
        "max_tokens": 500,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    
    # Получить прокси из файла
    proxy_dict = get_proxy_for_openai()
    
    if proxy_dict:
        logger.info(f"🔄 OpenAI request will use proxy")
    else:
        logger.warning("⚠️ OpenAI request WITHOUT proxy (may fail in Russia)")

    # Retry логика: 3 попытки с паузой
    last_error = None
    for attempt in range(3):
        try:
            # httpx.Client(proxies=...) принимает dict вида {"http://": "url", "https://": "url"}
            client_kwargs = {"timeout": 30.0}
            if proxy_dict:
                client_kwargs["proxies"] = proxy_dict
            
            with httpx.Client(**client_kwargs) as client:
                try:
                    r = client.post(
                        "https://api.openai.com/v1/chat/completions",
                        headers=headers,
                        json=payload,
                    )
                    r.raise_for_status()
                    data = r.json()
                except httpx.HTTPStatusError as e:
                    # Ловим HTTP ошибки от OpenAI (включая 400 с деталями)
                    info = {
                        "source": "openai",
                        "status_code": e.response.status_code if e.response else None,
                        "error": str(e),
                    }
                    if e.response is not None:
                        try:
                            info["data"] = e.response.json()
                        except Exception:
                            info["body"] = e.response.text
                    err = RuntimeError(f"OpenAI HTTP error {info.get('status_code')}")
                    err.openai_info = info
                    raise err
                
                # Безопасная распаковка
                if not data.get("choices"):
                    raise ValueError("Empty choices in GPT response")
                
                content = data["choices"][0].get("message", {}).get("content", "").strip()
                
                if not content:
                    raise ValueError("Empty content from GPT")
                
                logger.info(f"✅ GPT prompt generated (attempt {attempt + 1}): {content[:80]}...")
                return content
                
        except Exception as e:
            last_error = e
            logger.warning(f"⚠️ GPT attempt {attempt + 1} failed: {e}")
            if attempt < 2:  # не спим на последней попытке
                time.sleep(2)
    
    # Если все попытки провалились
    raise last_error or RuntimeError("GPT prompt generation failed")
