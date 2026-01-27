"""
RQ Worker для обработки задач из Redis
Запускается через: rq worker -c worker.rq_worker_config
"""
import os
import sys
import asyncio
import logging
from pathlib import Path

# Добавляем корень проекта в sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from worker.video_processor import process_video_generation

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)


def process_video_job(job_data: dict, **kwargs) -> dict:
    """
    Главная функция обработки задачи (вызывается из RQ)
    Это синхронная обертка над async функцией
    
    Args:
        job_data: {
            "job_id": str,
            "tg_user_id": int,
            "product_image_url": str,  # or "input_photo_path" for backwards compat
            "product_info": dict,
            "template_id": str,
            "extra_wishes": str | None
        }
        **kwargs: дополнительные параметры от RQ (timeout и т.д.)
    
    Returns:
        dict: {"success": bool, "output_url": str | None, "error": str | None}
    """
    logger.info(f"🚀 Starting job {job_data['job_id']}")
    
    # Запускаем async функцию в event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        result = loop.run_until_complete(process_video_generation(job_data))
        logger.info(f"✅ Job {job_data['job_id']} completed successfully")
        return result
    except Exception as e:
        logger.error(f"❌ Job {job_data['job_id']} failed: {e}", exc_info=True)
        return {
            "success": False,
            "output_url": None,
            "error": str(e)
        }
    finally:
        loop.close()
