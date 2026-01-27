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
    # Allow overriding model via env (fallback to sora-2-image-to-video)
    model = os.getenv("KIE_MODEL", "sora-2-image-to-video").strip() or "sora-2-image-to-video"

    payload = {
        "model": model,
        "input": {
            "prompt": f"{prompt}. Important: preserve the exact appearance of the product from the photo - color, shape, size, all details must match.",
            "image_urls": [image_url],
            "n_frames": "15",
            "aspect_ratio": "portrait",  # Вертикальный формат (9:16) для Reels/TikTok
            "remove_watermark": True,
        },
    }

    import logging
    logger = logging.getLogger(__name__)
    
    max_retries = 3
    retry_count = 0
    last_error = None
    
    with httpx.Client(timeout=90.0) as c:
        while retry_count < max_retries:
            try:
                logger.info(f"📤 Creating KIE task (attempt {retry_count + 1}/{max_retries})...")
                logger.debug(f"📋 KIE Request payload: model={model}, image_urls={payload['input']['image_urls']}, prompt_len={len(payload['input']['prompt'])}")
                r = c.post(KIE_CREATE_TASK_URL, headers=_auth_headers_json(api_key), json=payload)
                r.raise_for_status()
                data = r.json()
                # Some KIE endpoints return 200 HTTP but code!=200 in JSON
                try:
                    code_val = int(data.get("code", 200)) if isinstance(data.get("code", 200), (int, str)) else 200
                except Exception:
                    code_val = 200
                if code_val != 200:
                    msg = data.get("msg") or data.get("message") or "KIE error"
                    info = {"status_code": 200, "data": data, "attempt": retry_count + 1}
                    logger.warning(f"🔴 KIE JSON code {code_val}: {msg}")
                    err = RuntimeError(f"KIE API code {code_val}: {msg}")
                    err.kie_info = info
                    raise err
                logger.info(f"✅ KIE task created successfully")
                break
            except httpx.HTTPStatusError as e:
                retry_count += 1
                status_code = e.response.status_code if e.response else None
                
                # Пробуем достать тело ответа, чтобы корректно классифицировать ошибку
                info = {
                    "status_code": status_code,
                    "error": str(e),
                    "attempt": retry_count,
                }
                if e.response is not None:
                    try:
                        info["data"] = e.response.json()
                    except Exception:
                        info["body"] = e.response.text
                
                logger.warning(f"🔴 KIE HTTP error {status_code} (attempt {retry_count}/{max_retries}): {info}")
                logger.debug(f"📋 Request was: {payload['input']}")
                last_error = info
                
                # Retry на 500+ ошибках (server errors)
                if status_code and status_code >= 500 and retry_count < max_retries:
                    wait_time = 5 * retry_count  # 5s, 10s, 15s
                    logger.info(f"⏱️  KIE server error, retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                
                # На других ошибках — сразу fail
                err = RuntimeError(f"KIE HTTP error {status_code}")
                err.kie_info = info
                raise err
        else:
            # Исчерпаны все retry
            err = RuntimeError(f"KIE HTTP error {last_error.get('status_code')} after {max_retries} retries")
            err.kie_info = last_error
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

    # Увеличиваем HTTP timeout до 120s для медленных ответов KIE
    with httpx.Client(timeout=120.0) as c:
        last = None
        consecutive_errors = 0
        max_consecutive_errors = 5  # Увеличиваем до 5 попыток (включая timeout errors)
        
        while time.time() < deadline:
            poll_count += 1
            url = f"{KIE_RECORD_INFO_URL}?taskId={task_id}"
            try:
                r = c.get(url, headers={"Authorization": f"Bearer {api_key}"})
                r.raise_for_status()
                last = r.json()
                
                # 🔍 ЛОГИРУЕМ ВСЕ ОТВЕТЫ ДЛЯ ДЕБАГА (включая fail статусы)
                logger.debug(f"📡 Poll #{poll_count}: KIE response: {last}")
                
                # Парсим статус
                data = last.get("data") if isinstance(last, dict) else None
                status = ""
                if isinstance(data, dict):
                    status = (data.get("status") or data.get("state") or "").lower()
                else:
                    status = (last.get("status") or "").lower()
                
                # **ВАЖНО:** Check для fail ПЕРЕД reset counter
                if status in {"failed", "fail", "error"}:
                    logger.info(f"🔍 DEBUG: Poll #{poll_count} returned fail status, full response: {last}")
                    # НЕ сбрасываем счётчик - он будет увеличен ниже
                else:
                    # Только reset counter если статус НЕ fail (т.е. успех или waiting)
                    consecutive_errors = 0
                
            except httpx.TimeoutException as e:
                # HTTP request timeout (120s) - KIE не отвечает, но продолжаем polling
                consecutive_errors += 1
                logger.warning(f"⏱️ Poll #{poll_count}: HTTP timeout (consecutive: {consecutive_errors}/{max_consecutive_errors}), retrying...")
                
                if consecutive_errors >= max_consecutive_errors:
                    logger.error(f"❌ Too many consecutive timeouts ({max_consecutive_errors}), giving up")
                    info = {
                        "error": "http_timeout",
                        "taskId": task_id,
                        "poll_attempt": poll_count,
                        "message": "HTTP Client says - Request timeout error"
                    }
                    err = RuntimeError("HTTP Client says - Request timeout error")
                    err.kie_info = info
                    raise err
                
                time.sleep(15)  # Wait before retry
                continue
                
            except httpx.HTTPStatusError as e:
                consecutive_errors += 1
                status_code = e.response.status_code if e.response else None
                
                info = {
                    "status_code": status_code,
                    "error": str(e),
                    "taskId": task_id,
                    "poll_attempt": poll_count,
                }
                if e.response is not None:
                    try:
                        info["data"] = e.response.json()
                    except Exception:
                        info["body"] = e.response.text
                
                # На 500+ ошибках просто логируем и продолжаем
                if status_code and status_code >= 500:
                    logger.warning(f"🟠 Poll #{poll_count}: KIE server error {status_code} (consecutive: {consecutive_errors}/{max_consecutive_errors}), retrying...")
                    if consecutive_errors >= max_consecutive_errors:
                        logger.error(f"❌ Too many consecutive server errors ({max_consecutive_errors}), giving up")
                        err = RuntimeError(f"KIE server error {status_code}")
                        err.kie_info = info
                        raise err
                    time.sleep(10)  # Wait before retry
                    continue
                
                # На других ошибках — сразу fail
                logger.error(f"🔴 Poll #{poll_count}: KIE HTTP error {status_code}: {info}")
                err = RuntimeError(f"KIE HTTP error {status_code}")
                err.kie_info = info
                raise err

            # статус уже распарсен выше
            logger.info(f"⏳ Poll #{poll_count}: task={task_id[:8]}... status='{status}'")

            if status in {"success", "succeeded", "done", "completed", "finish", "finished"}:
                logger.info(f"✅ Poll #{poll_count}: SUCCESS - video ready!")
                return last
            
            if status in {"failed", "fail", "error", "canceled", "cancelled"}:
                fail_msg = data.get("failMsg") if isinstance(data, dict) else ""
                fail_code = data.get("failCode") if isinstance(data, dict) else ""
                
                logger.info(f"🔍 DEBUG Poll #{poll_count}: status='{status}', failCode={fail_code}, failMsg='{fail_msg}', consecutive_errors={consecutive_errors}")
                
                # Если это server error (5xx) - НЕ возвращаем сразу, продолжаем polling
                # KIE может временно упасть, но задача продолжит выполняться
                if isinstance(fail_code, (int, str)):
                    try:
                        fail_code_int = int(fail_code) if fail_code else 0
                        logger.info(f"🔍 DEBUG: fail_code_int={fail_code_int}, checking if >= 500")
                        if fail_code_int >= 500:
                            logger.warning(f"🟠 Poll #{poll_count}: KIE task has server error {fail_code} ('{fail_msg}'), will keep polling (may recover)...")
                            consecutive_errors += 1
                            logger.info(f"🔍 DEBUG: incremented consecutive_errors to {consecutive_errors}/{max_consecutive_errors}")
                            if consecutive_errors >= max_consecutive_errors:
                                logger.error(f"❌ Too many consecutive server errors, giving up")
                                logger.error(f"📋 Full KIE response on FAIL: {last}")
                                return last
                            time.sleep(15)  # Wait longer before next poll
                            continue
                    except (ValueError, TypeError) as e:
                        logger.info(f"🔍 DEBUG: fail_code conversion failed: {e}")
                        pass  # Если не число - обрабатываем как обычную ошибку
                
                # Остальные ошибки - финальны
                logger.error(f"❌ Poll #{poll_count}: FAILED - code={fail_code}, msg={fail_msg}")
                logger.error(f"📋 Full KIE response on FAIL: {last}")
                return last

            remaining_time = deadline - time.time()
            logger.debug(f"⏱️  Remaining time: {remaining_time:.0f}s, sleeping {interval_sec}s...")
            time.sleep(interval_sec)

        # таймаут — вернём последний ответ, чтобы увидеть статус/поля
        logger.warning(f"⏲️  Poll TIMEOUT after {poll_count} attempts, returning last response")
        return last or {"error": "timeout", "taskId": task_id}
