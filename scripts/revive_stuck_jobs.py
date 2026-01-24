#!/usr/bin/env python3
"""
Скрипт для "воскрешения" зависших задач
- Задачи в БД: processing, но воркер упал
- Задачи в Redis: failed/started, но не завершены
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db_adapter import get_pool, close_db_pool
from app.services.redis_queue import get_redis
from rq.job import Job
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    """Основная функция"""
    logger.info("🔍 Checking for stuck jobs...\n")
    
    pool = await get_pool()
    redis = get_redis()
    
    # Найти задачи в processing > 1 часа
    async with pool.acquire() as conn:
        stuck_jobs = await conn.fetch(
            """
            SELECT id, tg_user_id, status, created_at, started_at
            FROM jobs
            WHERE status IN ('processing', 'queued')
              AND created_at < NOW() - INTERVAL '1 hour'
            ORDER BY created_at
            """
        )
    
    if not stuck_jobs:
        logger.info("✅ No stuck jobs found")
        await close_db_pool()
        return
    
    logger.info(f"Found {len(stuck_jobs)} stuck jobs\n")
    
    for job_row in stuck_jobs:
        job_id = str(job_row['id'])
        tg_user_id = job_row['tg_user_id']
        status = job_row['status']
        
        logger.info(f"📋 Job {job_id[:8]}... (user {tg_user_id}, status: {status})")
        
        # Проверить статус в Redis
        try:
            rq_job = Job.fetch(job_id, connection=redis)
            redis_status = rq_job.get_status()
            logger.info(f"   Redis status: {redis_status}")
            
            if redis_status == 'failed':
                # Задача failed в Redis - пометить failed в БД
                async with pool.acquire() as conn:
                    await conn.execute(
                        """
                        UPDATE jobs
                        SET status = 'failed',
                            error = 'Worker crashed during processing',
                            finished_at = NOW()
                        WHERE id = $1
                        """,
                        job_id
                    )
                
                # Вернуть кредит
                async with pool.acquire() as conn:
                    await conn.execute(
                        """
                        UPDATE users
                        SET credits = credits + 1,
                            updated_at = NOW()
                        WHERE tg_user_id = $1
                        """,
                        tg_user_id
                    )
                
                logger.info(f"   ✅ Marked as failed, refunded 1 credit")
                
        except Exception as e:
            logger.warning(f"   ⚠️ Job not found in Redis: {e}")
            
            # Задачи нет в Redis вообще - значит queued, но не начата
            if status == 'queued':
                # Попробовать переставить в очередь
                from app.services.generation import start_generation
                
                async with pool.acquire() as conn:
                    job_data = await conn.fetchrow(
                        """
                        SELECT j.*, u.tg_user_id
                        FROM jobs j
                        JOIN users u ON j.user_id = u.id
                        WHERE j.id = $1
                        """,
                        job_id
                    )
                
                if job_data:
                    logger.info(f"   🔄 Re-enqueueing job...")
                    
                    # Удалить старую запись
                    async with pool.acquire() as conn:
                        await conn.execute("DELETE FROM jobs WHERE id = $1", job_id)
                    
                    # Создать новую (будет новый job_id, но те же данные)
                    try:
                        import json
                        product_info = job_data['product_info']
                        if isinstance(product_info, str):
                            product_info = json.loads(product_info)
                        
                        from app.services.generation import start_generation
                        # НЕ вызываем start_generation - это снимет еще кредит!
                        # Просто помечаем failed и возвращаем кредит
                        
                        async with pool.acquire() as conn:
                            await conn.execute(
                                """
                                UPDATE jobs
                                SET status = 'failed',
                                    error = 'Job stuck in queue, worker never picked it up',
                                    finished_at = NOW()
                                WHERE id = $1
                                """,
                                job_id
                            )
                            
                            await conn.execute(
                                """
                                UPDATE users
                                SET credits = credits + 1,
                                    updated_at = NOW()
                                WHERE tg_user_id = $1
                                """,
                                tg_user_id
                            )
                        
                        logger.info(f"   ✅ Marked as failed, refunded 1 credit")
                        
                    except Exception as restart_error:
                        logger.error(f"   ❌ Failed to restart: {restart_error}")
    
    logger.info(f"\n✅ Processed {len(stuck_jobs)} stuck jobs")
    await close_db_pool()


if __name__ == "__main__":
    asyncio.run(main())
