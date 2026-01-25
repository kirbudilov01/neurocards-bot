import os
import time
import httpx
from worker.kie_key_rotator import get_rotator

KIE_CREATE_TASK_URL = "https://api.kie.ai/api/v1/jobs/createTask"
KIE_RECORD_INFO_URL = "https://api.kie.ai/api/v1/jobs/recordInfo"


def _auth_headers_json(api_key: str):
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def create_task_sora_i2v(prompt: str, image_url: str) -> tuple[str, str]:
    """
    Создает задачу генерации видео в KIE.AI
    Returns: (task_id, api_key_used)
    """
    rotator = get_rotator()
    api_key = rotator.get_key()
    
    # Усиливаем соответствие входному изображению
    payload = {
        "model": "sora-2-image-to-video",
        "input": {
            "prompt": f"{prompt}. Important: preserve the exact appearance of the product from the photo - color, shape, size, all details must match.",
            "image_urls": [image_url],
            "n_frames": "15",
            "aspect_ratio": "portrait",  # Вертикальный формат (9:16) для Reels/TikTok
            "remove_watermark": True,
        },
    }

    with httpx.Client(timeout=90.0) as c:
        try:
            r = c.post(KIE_CREATE_TASK_URL, headers=_auth_headers_json(api_key), json=payload)
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPStatusError as e:
            # Пробуем достать тело ответа, чтобы корректно классифицировать ошибку
            info = {
                "status_code": e.response.status_code if e.response else None,
                "error": str(e),
            }
            if e.response is not None:
                try:
                    info["data"] = e.response.json()
                except Exception:
                    info["body"] = e.response.text
            err = RuntimeError(f"KIE HTTP error {info.get('status_code')}")
            err.kie_info = info
            raise err

    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"📋 KIE API response: {data}")

    # data может быть {"code": 200, "data": {...}} или {"recordId": ...}
    data_obj = data.get("data") if data.get("data") is not None else data
    
    task_id = (
        data_obj.get("recordId")
        or data_obj.get("taskId")
        or data_obj.get("id")
        or data.get("id")
    )
    
    return (task_id, api_key)


def poll_record_info(task_id: str, api_key: str, timeout_sec: int = 300, interval_sec: int = 10) -> dict:
    """
    Ждём до timeout_sec (по умолчанию 5 минут), опрашиваем каждые interval_sec секунд.
    Возвращаем последний JSON recordInfo (успех/ошибка/таймаут).
    """
    import logging
    logger = logging.getLogger(__name__)
    
    if not task_id:
        raise RuntimeError("Empty task_id")

    deadline = time.time() + timeout_sec
    poll_count = 0

    with httpx.Client(timeout=60.0) as c:
        last = None
        while time.time() < deadline:
            poll_count += 1
            url = f"{KIE_RECORD_INFO_URL}?taskId={task_id}"
            try:
                r = c.get(url, headers={"Authorization": f"Bearer {api_key}"})
                r.raise_for_status()
                last = r.json()
                
                # 🔍 ЛОГИРУЕМ ВСЕ ОТВЕТЫ ДЛЯ ДЕБАГА
                logger.debug(f"📡 Poll #{poll_count}: KIE response: {last}")
                
            except httpx.HTTPStatusError as e:
                info = {
                    "status_code": e.response.status_code if e.response else None,
                    "error": str(e),
                    "taskId": task_id,
                }
                if e.response is not None:
                    try:
                        info["data"] = e.response.json()
                    except Exception:
                        info["body"] = e.response.text
                logger.error(f"🔴 Poll #{poll_count}: KIE HTTP error {info.get('status_code')}: {info}")
                err = RuntimeError(f"KIE HTTP error {info.get('status_code')}")
                err.kie_info = info
                raise err

            # статус может лежать в разных местах — проверим популярные
            data = last.get("data") if isinstance(last, dict) else None
            status = ""
            if isinstance(data, dict):
                status = (data.get("status") or data.get("state") or "").lower()
            else:
                status = (last.get("status") or "").lower()

            # 🎯 ЛОГИРУЕМ СТАТУС
            logger.info(f"⏳ Poll #{poll_count}: task={task_id[:8]}... status='{status}'")

            if status in {"success", "succeeded", "done", "completed", "finish", "finished"}:
                logger.info(f"✅ Poll #{poll_count}: SUCCESS - video ready!")
                return last
            if status in {"failed", "error", "canceled", "cancelled"}:
                fail_msg = data.get("failMsg") if isinstance(data, dict) else ""
                fail_code = data.get("failCode") if isinstance(data, dict) else ""
                logger.error(f"❌ Poll #{poll_count}: FAILED - code={fail_code}, msg={fail_msg}")
                return last

            remaining_time = deadline - time.time()
            logger.debug(f"⏱️  Remaining time: {remaining_time:.0f}s, sleeping {interval_sec}s...")
            time.sleep(interval_sec)

        # таймаут — вернём последний ответ, чтобы увидеть статус/поля
        logger.warning(f"⏲️  Poll TIMEOUT after {poll_count} attempts, returning last response")
        return last or {"error": "timeout", "taskId": task_id}
