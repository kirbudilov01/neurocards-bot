"""
Redis Queue Service
Управление очередью задач через Redis
"""
import os
import logging
from typing import Optional
import json
from redis import Redis
from rq import Queue
from rq.job import Job

logger = logging.getLogger(__name__)


def get_redis_connection() -> Redis:
    """Получить подключение к Redis с увеличенными таймаутами"""
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    # Увеличиваем таймауты для долгих задач (30 минут)
    return Redis.from_url(
        redis_url, 
        decode_responses=True,
        socket_timeout=1800,  # 30 минут
        socket_connect_timeout=30,  # 30 секунд на подключение
        socket_keepalive=True,  # Keep-alive для стабильности
        health_check_interval=30  # Проверка здоровья каждые 30 сек
    )


def get_queue(name: str = "neurocards") -> Queue:
    """Получить очередь задач"""
    redis_conn = get_redis_connection()
    # default_timeout=1800 (30 минут) - для всех jobs в очереди
    return Queue(name, connection=redis_conn, default_timeout=1800)


def enqueue_job(
    job_id: str,
    tg_user_id: int,
    input_photo_path: str,
    product_info: dict,
    template_id: str = "ugc",
    extra_wishes: Optional[str] = None,
) -> str:
    """
    Добавить задачу в очередь Redis
    
    Returns:
        job_id (str): ID задачи в Redis
    """
    queue = get_queue()
    
    # Данные задачи
    job_data = {
        "job_id": job_id,
        "tg_user_id": tg_user_id,
        "input_photo_path": input_photo_path,
        "product_info": product_info,
        "template_id": template_id,
        "extra_wishes": extra_wishes,
    }
    
    # Добавляем в очередь с ID для идемпотентности
    job = queue.enqueue(
        "worker.rq_worker.process_video_job",  # Полный путь к функции
        job_data,
        job_id=job_id,  # Используем наш UUID как ID в Redis
        timeout=1800,  # Таймаут 30 минут на обработку (в секундах)
        result_ttl=3600,  # Результат храним 1 час
        failure_ttl=86400,  # Ошибки храним 24 часа
    )
    
    logger.info(f"✅ Job {job_id} enqueued to Redis, position: {queue.count}")
    return job.id


def get_job_status(job_id: str) -> dict:
    """
    Получить статус задачи из Redis
    
    Returns:
        dict: {
            "status": "queued" | "processing" | "done" | "failed",
            "position": int (если queued),
            "error": str (если failed),
            "result": dict (если done)
        }
    """
    redis_conn = get_redis_connection()
    
    try:
        job = Job.fetch(job_id, connection=redis_conn)
        
        # Маппинг статусов RQ -> наши статусы
        status_map = {
            "queued": "queued",
            "started": "processing",
            "finished": "done",
            "failed": "failed",
            "deferred": "queued",
            "scheduled": "queued",
        }
        
        status = status_map.get(job.get_status(), "queued")
        
        result = {
            "status": status,
        }
        
        # Позиция в очереди
        if status == "queued":
            queue = get_queue()
            position = queue.get_job_position(job_id)
            if position is not None:
                result["position"] = position + 1  # +1 для user-friendly нумерации
        
        # Ошибка
        if status == "failed" and job.exc_info:
            result["error"] = str(job.exc_info)
        
        # Результат
        if status == "done" and job.result:
            result["result"] = job.result
        
        return result
        
    except Exception as e:
        logger.error(f"Failed to get job status for {job_id}: {e}")
        return {"status": "queued", "error": str(e)}


def get_queue_stats() -> dict:
    """
    Получить статистику очереди
    
    Returns:
        dict: {
            "queued": int,
            "processing": int,
            "failed": int,
            "workers": int
        }
    """
    queue = get_queue()
    redis_conn = get_redis_connection()
    
    from rq.registry import StartedJobRegistry, FailedJobRegistry
    
    started_registry = StartedJobRegistry(queue=queue)
    failed_registry = FailedJobRegistry(queue=queue)
    
    return {
        "queued": len(queue),
        "processing": len(started_registry),
        "failed": len(failed_registry),
        "workers": len(queue.workers),
    }
