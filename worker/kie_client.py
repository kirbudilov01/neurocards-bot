import os
import time
import httpx

KIE_API_KEY = os.getenv("KIE_API_KEY", "")
KIE_CREATE_TASK_URL = "https://api.kie.ai/api/v1/jobs/createTask"
KIE_RECORD_INFO_URL = "https://api.kie.ai/api/v1/jobs/recordInfo"


def _auth_headers_json():
    if not KIE_API_KEY:
        raise RuntimeError("Missing env var: KIE_API_KEY")
    return {
        "Authorization": f"Bearer {KIE_API_KEY}",
        "Content-Type": "application/json",
    }


def create_task_sora_i2v(prompt: str, image_url: str) -> str:
    payload = {
        "model": "sora-2-image-to-video",
        "input": {
            "prompt": prompt,
            "image_urls": [image_url],
            "aspect_ratio": "portrait",
            "n_frames": "15",
            "remove_watermark": True,
        },
    }

    with httpx.Client(timeout=90.0) as c:
        r = c.post(KIE_CREATE_TASK_URL, headers=_auth_headers_json(), json=payload)
        r.raise_for_status()
        data = r.json()

    # в blueprint recordId используется как taskId
    return data["data"]["recordId"]


def poll_record_info(task_id: str, timeout_sec: int = 600) -> dict:
    """
    v1: возвращаем ответ recordInfo (сырой JSON) чтобы увидеть структуру.
    v2: сделаем ожидание по status и вытащим mp4 URL.
    """
    deadline = time.time() + timeout_sec

    with httpx.Client(timeout=60.0) as c:
        while time.time() < deadline:
            url = f"{KIE_RECORD_INFO_URL}?taskId={task_id}"
            r = c.get(url, headers={"Authorization": f"Bearer {KIE_API_KEY}"})
            r.raise_for_status()
            return r.json()

    raise RuntimeError("Kie timeout waiting recordInfo")
