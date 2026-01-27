"""
Адаптер базы данных с поддержкой как Supabase, так и прямого PostgreSQL
"""
from __future__ import annotations

import asyncio
import logging
import os
from functools import partial
from typing import Any, Callable, Dict, Optional, TypeVar

T = TypeVar("T")

logger = logging.getLogger(__name__)


async def run_blocking(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Runs a synchronous function in a separate thread to prevent blocking the event loop."""
    return await asyncio.to_thread(func, *args, **kwargs)


# Определяем тип базы данных
USE_POSTGRES = os.getenv("USE_POSTGRES", "false").lower() == "true"
DATABASE_TYPE = os.getenv("DATABASE_TYPE", "postgres").lower()  # Default to postgres (Supabase removed)

if USE_POSTGRES or DATABASE_TYPE == "postgres":
    # Используем прямое подключение к PostgreSQL через asyncpg
    import asyncpg
    from asyncpg import Pool
    
    # Глобальный пул подключений
    _pool: Optional[Pool] = None
    
    async def init_db_pool() -> Pool:
        """Инициализирует пул подключений к PostgreSQL"""
        global _pool
        if _pool is None:
            database_url = os.getenv("DATABASE_URL")
            if not database_url:
                raise ValueError("DATABASE_URL environment variable is required for PostgreSQL mode")
            
            _pool = await asyncpg.create_pool(
                database_url,
                min_size=2,
                max_size=10,
                command_timeout=60
            )
            logger.info("✅ PostgreSQL pool initialized")
        return _pool
    
    async def get_pool() -> Pool:
        """Возвращает пул подключений (создает если не существует)"""
        if _pool is None:
            return await init_db_pool()
        return _pool
    
    async def close_db_pool():
        """Закрывает пул подключений"""
        global _pool
        if _pool:
            await _pool.close()
            _pool = None
            logger.info("✅ PostgreSQL pool closed")

else:
    # PostgreSQL is required - Supabase support removed
    raise RuntimeError(
        "USE_POSTGRES must be 'true'. Supabase support has been removed. "
        "Please set USE_POSTGRES=true and configure PostgreSQL connection."
    )


# ---------------- USERS ----------------

async def get_or_create_user(tg_user_id: int, username: Optional[str] = None) -> Dict[str, Any]:
    """Получает или создает пользователя"""
    
    if DATABASE_TYPE == "postgres":
        pool = await get_pool()
        async with pool.acquire() as conn:
            # Пытаемся найти пользователя
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE tg_user_id = $1",
                tg_user_id
            )
            
            if row:
                user = dict(row)
                # Обновляем username если изменился
                if username and user.get("username") != username:
                    await conn.execute(
                        "UPDATE users SET username = $1 WHERE tg_user_id = $2",
                        username, tg_user_id
                    )
                    user["username"] = username
                return user
            
            # Создаем нового пользователя с 2 бесплатными токенами
            row = await conn.fetchrow(
                """
                INSERT INTO users (tg_user_id, username, credits)
                VALUES ($1, $2, $3)
                RETURNING *
                """,
                tg_user_id, username, 2  # ✅ ДАТЬ 2 БЕСПЛАТНЫХ ТОКЕНА
            )
            logger.info(f"🎉 New user {tg_user_id} created with 2 free tokens")
            return dict(row)
    
    else:
        # Fallback to PostgreSQL (Supabase support removed)
        logger.warning("DATABASE_TYPE not set to 'postgres', falling back to PostgreSQL mode")
        return await get_or_create_user(tg_user_id, username)


async def get_user_by_tg_id(tg_user_id: int) -> Optional[Dict[str, Any]]:
    """Получает пользователя по Telegram ID"""
    
    if DATABASE_TYPE == "postgres":
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE tg_user_id = $1",
                tg_user_id
            )
            return dict(row) if row else None
    
    else:
        res = await run_blocking(
            supabase.table("users")
            .select("*")
            .eq("tg_user_id", tg_user_id)
            .limit(1)
            .execute
        )
        return res.data[0] if res.data else None


# ---------------- JOBS ----------------

async def create_job_and_consume_credit(
    tg_user_id: int,
    template_type: str,
    idempotency_key: str,
    photo_path: str,
    prompt_input: str
) -> Dict[str, Any]:
    """Создает задание и списывает кредит атомарно"""
    
    if DATABASE_TYPE == "postgres":
        pool = await get_pool()
        async with pool.acquire() as conn:
            # Вызываем RPC функцию
            row = await conn.fetchrow(
                "SELECT * FROM create_job_and_consume_credit($1, $2, $3, $4, $5)",
                tg_user_id, template_type, idempotency_key, photo_path, prompt_input
            )
            
            if not row:
                raise Exception("Insufficient credits or duplicate job")
            
            # RPC возвращает JSON в первой колонке
            result_json = row[0]
            if isinstance(result_json, str):
                import json
                return json.loads(result_json)
            return result_json
    
    else:
        res = await run_blocking(
            supabase.rpc(
                "create_job_and_consume_credit",
                {
                    "p_tg_user_id": tg_user_id,
                    "p_template_type": template_type,
                    "p_idempotency_key": idempotency_key,
                    "p_photo_path": photo_path,
                    "p_prompt_input": prompt_input,
                }
            ).execute
        )
        if not res.data:
            raise Exception("Insufficient credits or duplicate job")
        return res.data


async def get_job_by_id(job_id: int) -> Optional[Dict[str, Any]]:
    """Получает задание по ID"""
    
    if DATABASE_TYPE == "postgres":
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM jobs WHERE id = $1",
                job_id
            )
            return dict(row) if row else None
    
    else:
        res = await run_blocking(
            supabase.table("jobs")
            .select("*")
            .eq("id", job_id)
            .limit(1)
            .execute
        )
        return res.data[0] if res.data else None


async def update_job_status(
    job_id: int,
    status: str,
    result_video_path: Optional[str] = None,
    error_message: Optional[str] = None
):
    """Обновляет статус задания"""
    
    if DATABASE_TYPE == "postgres":
        pool = await get_pool()
        async with pool.acquire() as conn:
            query = "UPDATE jobs SET status = $1"
            params = [status]
            param_idx = 2
            
            # Устанавливаем started_at при переходе в processing
            if status == 'processing':
                query += ", started_at = NOW()"
            # Устанавливаем finished_at при завершении
            elif status in ('done', 'failed'):
                query += ", finished_at = NOW()"
            
            if result_video_path is not None:
                query += f", result_video_path = ${param_idx}"
                params.append(result_video_path)
                param_idx += 1
            
            if error_message is not None:
                query += f", error_message = ${param_idx}"
                params.append(error_message)
                param_idx += 1
            
            query += f" WHERE id = ${param_idx}"
            params.append(job_id)
            
            await conn.execute(query, *params)
    
    else:
        update_data = {"status": status}
        if result_video_path is not None:
            update_data["result_video_path"] = result_video_path
        if error_message is not None:
            update_data["error_message"] = error_message
        
        await run_blocking(
            supabase.table("jobs")
            .update(update_data)
            .eq("id", job_id)
            .execute
        )


async def get_user_jobs(tg_user_id: int, limit: int = 10) -> list[Dict[str, Any]]:
    """Получает последние задания пользователя"""
    
    if DATABASE_TYPE == "postgres":
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM jobs
                WHERE tg_user_id = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                tg_user_id, limit
            )
            return [dict(row) for row in rows]
    
    else:
        res = await run_blocking(
            supabase.table("jobs")
            .select("*")
            .eq("tg_user_id", tg_user_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute
        )
        return res.data


async def refund_credit(tg_user_id: int) -> None:
    """Возвращает 1 кредит пользователю"""
    
    if DATABASE_TYPE == "postgres":
        pool = await get_pool()
        async with pool.acquire() as conn:
            result = await conn.fetchval(
                "SELECT refund_credit($1)",
                tg_user_id
            )
            logger.info(f"💰 Refund 1 credit to user {tg_user_id}, new balance: {result}")
    
    else:
        await run_blocking(
            supabase.rpc("refund_credit", {"p_tg_user_id": tg_user_id}).execute
        )


async def add_credits(tg_user_id: int, amount: int, operation_type: str = "bonus") -> int:
    """Добавляет кредиты пользователю. Возвращает новый баланс."""
    
    if amount <= 0:
        raise ValueError("Amount must be positive")
    
    if DATABASE_TYPE == "postgres":
        pool = await get_pool()
        async with pool.acquire() as conn:
            result = await conn.fetchval(
                "SELECT add_credits($1, $2, $3)",
                tg_user_id,
                amount,
                operation_type
            )
            logger.info(f"➕ Added {amount} credits ({operation_type}) to user {tg_user_id}, new balance: {result}")
            return result
    
    else:
        result = await run_blocking(
            supabase.rpc("add_credits", {
                "p_tg_user_id": tg_user_id, 
                "p_amount": amount,
                "p_operation_type": operation_type
            }).execute
        )
        return result.data[0] if result.data else 0


# ============ Phase 2: Retry & Error Handling ============

async def increment_job_retry(job_id: str) -> int:
    """
    Увеличивает счетчик retry попыток для job
    Возвращает новое значение retry_count
    """
    if DATABASE_TYPE == "postgres":
        pool = await get_pool()
        async with pool.acquire() as conn:
            # Проверяем есть ли колонка retry_count, если нет - возвращаем 0
            row = await conn.fetchrow(
                """
                UPDATE jobs 
                SET retry_count = COALESCE(retry_count, 0) + 1
                WHERE id = $1
                RETURNING COALESCE(retry_count, 1) as retry_count
                """,
                job_id
            )
            return row['retry_count'] if row else 1
    else:
        # Supabase - через RPC или прямой UPDATE
        res = await run_blocking(
            supabase.table("jobs")
            .select("retry_count")
            .eq("id", job_id)
            .execute
        )
        current = (res.data[0].get("retry_count") or 0) if res.data else 0
        new_count = current + 1
        
        await run_blocking(
            supabase.table("jobs")
            .update({"retry_count": new_count})
            .eq("id", job_id)
            .execute
        )
        return new_count


async def mark_job_failed_with_refund(
    job_id: str,
    tg_user_id: int,
    error_message: str
) -> None:
    """
    Помечает job как failed + возвращает кредит пользователю
    Используется при критических ошибках (USER_VIOLATION, BILLING, превышен retry)
    """
    # Обновляем статус job
    await update_job_status(job_id, "failed", error_message=error_message)
    
    # Возвращаем кредит
    await refund_credit(tg_user_id)
    
    logger.info(f"❌ Job {job_id} marked as failed, credit refunded to user {tg_user_id}")


# ---------------- WORKER FUNCTIONS ----------------

async def fetch_next_queued_job() -> Optional[Dict[str, Any]]:
    """Получает следующее задание из очереди (для worker'а)
    
    ВАЖНО: Не обновляет статус! Worker сам вызовет update_job(status='processing')
    Это предотвращает race condition если несколько worker'ов запущены.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    if DATABASE_TYPE == "postgres":
        pool = await get_pool()
        async with pool.acquire() as conn:
            # Получаем первый queued job БЕЗ UPDATE
            # FOR UPDATE SKIP LOCKED предотвращает другим worker'ам брать этот job
            row = await conn.fetchrow(
                """
                SELECT * FROM jobs
                WHERE status = 'queued'
                ORDER BY created_at ASC
                FOR UPDATE SKIP LOCKED
                LIMIT 1
                """
            )
            if row:
                job_dict = dict(row)
                logger.info(f"✅ Fetched job {job_dict.get('id', 'unknown')} from queue (status will be set by worker)")
                return job_dict
            else:
                logger.debug("⏳ No queued jobs found")
                return None
    
    else:
        res = await run_blocking(
            supabase.table("jobs")
            .select("*")
            .eq("status", "queued")
            .order("created_at")
            .limit(1)
            .execute
        )
        
        if not res.data:
            return None
        
        job = res.data[0]
        await run_blocking(
            supabase.table("jobs")
            .update({"status": "processing"})
            .eq("id", job["id"])
            .execute
        )
        return job


# ---------------- ДОПОЛНИТЕЛЬНЫЕ ФУНКЦИИ (для generation.py и др.) ----------------

async def get_job_by_idempotency_key(idempotency_key: str) -> Optional[Dict[str, Any]]:
    """Проверяет существование задания по idempotency ключу"""
    
    if DATABASE_TYPE == "postgres":
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM jobs WHERE idempotency_key = $1",
                idempotency_key
            )
            return dict(row) if row else None
    
    else:
        res = await run_blocking(
            supabase.table("jobs")
            .select("*")
            .eq("idempotency_key", idempotency_key)
            .limit(1)
            .execute
        )
        return res.data[0] if res.data else None


async def get_queue_position(job_id: int) -> int:
    """Возвращает позицию задания в очереди"""
    
    if DATABASE_TYPE == "postgres":
        pool = await get_pool()
        async with pool.acquire() as conn:
            # Получаем created_at задания
            job_row = await conn.fetchrow(
                "SELECT created_at FROM jobs WHERE id = $1",
                job_id
            )
            if not job_row:
                return 1
            
            created_at = job_row["created_at"]
            
            # Считаем сколько queued/processing заданий создано раньше
            count = await conn.fetchval(
                """
                SELECT COUNT(*) FROM jobs
                WHERE status IN ('queued', 'processing')
                AND created_at < $1
                """,
                created_at
            )
            return (count or 0) + 1
    
    else:
        j = await run_blocking(
            supabase.table("jobs")
            .select("created_at")
            .eq("id", job_id)
            .limit(1)
            .execute
        )
        if not j.data:
            return 1
        created_at = j.data[0]["created_at"]
        
        r = await run_blocking(
            supabase.table("jobs")
            .select("id")
            .in_("status", ["queued", "processing"])
            .lt("created_at", created_at)
            .execute
        )
        return (len(r.data) if r.data else 0) + 1


async def safe_get_balance(tg_user_id: int) -> int:
    """
    Безопасно получает баланс пользователя (с timeout и обработкой ошибок)
    Возвращает 0 при ошибке
    """
    try:
        user = await asyncio.wait_for(
            get_user_by_tg_id(tg_user_id),
            timeout=5.0
        )
        if user:
            # Поддерживаем оба названия поля для совместимости
            return user.get("credits") or user.get("balance", 0)
        return 0
    except Exception as e:
        logger.error(f"Failed to get balance for user {tg_user_id}: {e}")
        return 0


async def list_last_jobs(tg_user_id: int, limit: int = 5) -> list[Dict[str, Any]]:
    """Возвращает последние задания пользователя"""
    
    if DATABASE_TYPE == "postgres":
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, template_type as kind, status, created_at, 
                       result_video_path as output_url, error_message as error,
                       template_type as template_id
                FROM jobs
                WHERE tg_user_id = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                tg_user_id, limit
            )
            return [dict(row) for row in rows]
    
    else:
        # Для Supabase нужно сначала получить user_id
        user = await get_user_by_tg_id(tg_user_id)
        if not user:
            return []
        
        user_id = user.get("id")
        
        res = await run_blocking(
            supabase.table("jobs")
            .select("id,kind,status,created_at,output_url,error,template_id")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute
        )
        return res.data or []


# ========== АЛИАСЫ ДЛЯ ОБРАТНОЙ СОВМЕСТИМОСТИ ==========
# Для старого кода, который использует другие имена функций

# Новая функция для worker.py (принимает dict с полями для обновления)
async def update_job(job_id: str, updates: Dict[str, Any]):
    """
    Обновляет задание с произвольным набором полей
    Используется worker.py с новой системой обработки ошибок
    
    ВАЖНО: Для timestamp полей передавайте строку "NOW()" чтобы использовать SQL NOW()
    """
    if DATABASE_TYPE == "postgres":
        pool = await get_pool()
        async with pool.acquire() as conn:
            # Формируем динамический UPDATE запрос
            set_parts = []
            params = []
            
            for key, value in updates.items():
                # Для "NOW()" вставляем напрямую в SQL
                if isinstance(value, str) and value == "NOW()":
                    set_parts.append(f"{key} = NOW()")
                else:
                    set_parts.append(f"{key} = ${len(params) + 1}")
                    params.append(value)
            
            if not set_parts:
                return  # Нечего обновлять
            
            # job_id всегда последний параметр
            params.append(job_id)
            query = f"UPDATE jobs SET {', '.join(set_parts)} WHERE id = ${len(params)}"
            
            await conn.execute(query, *params)
    else:
        # Supabase версия
        clean_updates = {}
        for key, value in updates.items():
            if isinstance(value, str) and value == "NOW()":
                from datetime import datetime, timezone
                clean_updates[key] = datetime.now(timezone.utc).isoformat()
            else:
                clean_updates[key] = value
        
        await run_blocking(
            lambda: supabase.table("jobs").update(clean_updates).eq("id", job_id).execute()
        )

# Алиас для handlers/services
create_job = create_job_and_consume_credit
get_user = get_user_by_tg_id
