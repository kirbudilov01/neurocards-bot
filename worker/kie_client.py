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
    
    payload = {
        "model": "sora-2-image-to-video",
        "input": {
            "prompt": prompt,
            "image_urls": [image_url],
            "aspect_ratio": "9:16",
            "n_frames": "15",
            "remove_watermark": True,
        },
    }

    with httpx.Client(timeout=90.0) as c:
        r = c.post(KIE_CREATE_TASK_URL, headers=_auth_headers_json(api_key), json=payload)
        r.raise_for_status()
        data = r.json()

    task_id = (
        data.get("data", {}).get("recordId")
        or data.get("data", {}).get("taskId")
        or data.get("data", {}).get("id")
        or data.get("recordId")
        or data.get("taskId")
        or data.get("id")
    )
    
    return (task_id, api_key)


def poll_record_info(task_id: str, api_key: str, timeout_sec: int = 300, interval_sec: int = 10) -> dict:
    """
    Ждём до timeout_sec (по умолчанию 5 минут), опрашиваем каждые interval_sec секунд.
    Возвращаем последний JSON recordInfo (успех/ошибка/таймаут).
    """
    if not task_id:
        raise RuntimeError("Empty task_id")

    deadline = time.time() + timeout_sec

    with httpx.Client(timeout=60.0) as c:
        last = None
        while time.time() < deadline:
            url = f"{KIE_RECORD_INFO_URL}?taskId={task_id}"
            r = c.get(url, headers={"Authorization": f"Bearer {api_key}"})
            r.raise_for_status()
            last = r.json()

            # статус может лежать в разных местах — проверим популярные
            data = last.get("data") if isinstance(last, dict) else None
            status = ""
            if isinstance(data, dict):
                status = (data.get("status") or data.get("state") or "").lower()
            else:
                status = (last.get("status") or "").lower()

            if status in {"success", "succeeded", "done", "completed", "finish", "finished"}:
                return last
            if status in {"failed", "error", "canceled", "cancelled"}:
                return last

            time.sleep(interval_sec)

        # таймаут — вернём последний ответ, чтобы увидеть статус/поля
        return last or {"error": "timeout", "taskId": task_id}
