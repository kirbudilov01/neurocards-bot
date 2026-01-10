from __future__ import annotations

import asyncio
import logging
from functools import partial
from typing import Any, Callable, Dict, Optional, TypeVar

from supabase import create_client, Client

T = TypeVar("T")

logger = logging.getLogger(__name__)


async def run_blocking(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Runs a synchronous function in a separate thread to prevent blocking the event loop."""
    return await asyncio.to_thread(func, *args, **kwargs)


from app.config import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY

supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


# ---------------- USERS ----------------
async def get_or_create_user(tg_user_id: int, username: Optional[str] = None) -> Dict[str, Any]:
    res = await run_blocking(
        supabase.table("users")
        .select("*")
        .eq("tg_user_id", tg_user_id)
        .limit(1)
        .execute
    )
    if res.data:
        # опционально обновим username
        if username and res.data[0].get("username") != username:
            await run_blocking(
                supabase.table("users")
                .update({"username": username})
                .eq("tg_user_id", tg_user_id)
                .execute
            )
        return res.data[0]

    # новый пользователь (значение по умолчанию должно быть в базе: credits/balance default)
    ins = await run_blocking(
        supabase.table("users")
        .insert({"tg_user_id": tg_user_id, "username": username})
        .execute
    )
    return ins.data[0]


async def get_user_balance(tg_user_id: int) -> int:
    """
    Поддерживаем оба поля:
    - users.balance
    - users.credits
    """
    r = await run_blocking(
        supabase.table("users")
        .select("*")
        .eq("tg_user_id", tg_user_id)
        .limit(1)
        .execute
    )
    if not r.data:
        return 0
    row = r.data[0] or {}

    if row.get("balance") is not None:
        return int(row.get("balance") or 0)
    if row.get("credits") is not None:
        return int(row.get("credits") or 0)
    return 0


async def safe_get_balance(tg_user_id: int) -> int:
    """
    Safely retrieves the user's balance with a timeout and error handling.
    Returns 0 if the query fails or times out.
    """
    try:
        return await asyncio.wait_for(get_user_balance(tg_user_id), timeout=5.0)
    except Exception:
        logger.error(f"Failed to get balance for user {tg_user_id}", exc_info=True)
        return 0


# ---------------- JOBS ----------------
async def get_job_by_idempotency_key(idempotency_key: str) -> Optional[Dict[str, Any]]:
    """
    Checks if a job with the given idempotency key already exists.
    """
    res = await run_blocking(
        supabase.table("jobs")
        .select("id")
        .eq("idempotency_key", idempotency_key)
        .limit(1)
        .execute
    )
    return res.data[0] if res.data else None


async def create_job_and_consume_credit(
    tg_user_id: int,
    idempotency_key: str,
    kind: str,
    input_photo_path: str,
    product_info: Dict[str, Any],
    extra_wishes: str | None,
    template_id: str = "ugc",
) -> Dict[str, Any]:
    """
    Calls the RPC function to create a job and consume a credit in a single transaction.
    """
    params = {
        "p_tg_user_id": tg_user_id,
        "p_idempotency_key": idempotency_key,
        "p_kind": kind,
        "p_input_photo_path": input_photo_path,
        "p_product_info": product_info,
        "p_extra_wishes": extra_wishes,
        "p_template_id": template_id,
    }
    res = await run_blocking(
        supabase.rpc, "create_job_and_consume_credit", params
    )
    return res.data[0]


async def update_job_status(job_id: str, status: str, **fields: Any) -> None:
    payload = {"status": status, **fields}
    await run_blocking(
        supabase.table("jobs").update(payload).eq("id", job_id).execute
    )


async def fetch_next_queued_job() -> Optional[Dict[str, Any]]:
    """
    MVP без SKIP LOCKED: берем самый ранний queued.
    Для одного воркера этого достаточно.
    """
    res = await run_blocking(
        supabase.table("jobs")
        .select("*")
        .eq("status", "queued")
        .order("created_at", desc=False)
        .limit(1)
        .execute
    )
    return res.data[0] if res.data else None


async def get_queue_position(job_id: str) -> int:
    """
    Позиция в очереди: сколько queued/processing задач создано раньше этой + 1.
    MVP-версия.
    """
    j = await run_blocking(
        supabase.table("jobs").select("created_at").eq("id", job_id).limit(1).execute
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


# ---------------- HELPERS ----------------
async def get_user_by_id(user_id: str) -> Dict[str, Any]:
    res = await run_blocking(
        supabase.table("users").select("*").eq("id", user_id).limit(1).execute
    )
    return res.data[0]


async def list_last_jobs(tg_user_id: int, limit: int = 5) -> list[dict]:
    u = await run_blocking(
        supabase.table("users").select("id").eq("tg_user_id", tg_user_id).limit(1).execute
    )
    if not u.data:
        return []
    user_id = u.data[0]["id"]

    r = await run_blocking(
        supabase.table("jobs")
        .select("id,kind,status,created_at,output_url,error,template_id")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute
    )
    return r.data or []
