from __future__ import annotations

from typing import Any, Dict, Optional

from supabase import create_client, Client
from app.config import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY

supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


# ---------------- USERS ----------------
def get_or_create_user(tg_user_id: int, username: Optional[str] = None) -> Dict[str, Any]:
    res = (
        supabase.table("users")
        .select("*")
        .eq("tg_user_id", tg_user_id)
        .limit(1)
        .execute()
    )
    if res.data:
        # опционально обновим username
        if username and res.data[0].get("username") != username:
            supabase.table("users").update({"username": username}).eq("tg_user_id", tg_user_id).execute()
        return res.data[0]

    # новый пользователь (значение по умолчанию должно быть в базе: credits/balance default)
    ins = (
        supabase.table("users")
        .insert({"tg_user_id": tg_user_id, "username": username})
        .execute()
    )
    return ins.data[0]


def get_user_balance(tg_user_id: int) -> int:
    """
    Поддерживаем оба поля:
    - users.balance
    - users.credits
    """
    r = supabase.table("users").select("*").eq("tg_user_id", tg_user_id).limit(1).execute()
    if not r.data:
        return 0
    row = r.data[0] or {}

    if row.get("balance") is not None:
        return int(row.get("balance") or 0)
    if row.get("credits") is not None:
        return int(row.get("credits") or 0)
    return 0


# ---------------- JOBS ----------------
def get_job_by_idempotency_key(idempotency_key: str) -> Optional[Dict[str, Any]]:
    """
    Checks if a job with the given idempotency key already exists.
    """
    res = (
        supabase.table("jobs")
        .select("id")
        .eq("idempotency_key", idempotency_key)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def create_job_and_consume_credit(
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
    res = supabase.rpc("create_job_and_consume_credit", params).execute()
    return res.data[0]


def update_job_status(job_id: str, status: str, **fields: Any) -> None:
    payload = {"status": status, **fields}
    supabase.table("jobs").update(payload).eq("id", job_id).execute()


def fetch_next_queued_job() -> Optional[Dict[str, Any]]:
    """
    MVP без SKIP LOCKED: берем самый ранний queued.
    Для одного воркера этого достаточно.
    """
    res = (
        supabase.table("jobs")
        .select("*")
        .eq("status", "queued")
        .order("created_at", desc=False)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def get_queue_position(job_id: str) -> int:
    """
    Позиция в очереди: сколько queued/processing задач создано раньше этой + 1.
    MVP-версия.
    """
    j = supabase.table("jobs").select("created_at").eq("id", job_id).limit(1).execute()
    if not j.data:
        return 1
    created_at = j.data[0]["created_at"]

    r = (
        supabase.table("jobs")
        .select("id")
        .in_("status", ["queued", "processing"])
        .lt("created_at", created_at)
        .execute()
    )
    return (len(r.data) if r.data else 0) + 1


# ---------------- HELPERS ----------------
def get_user_by_id(user_id: str) -> Dict[str, Any]:
    res = supabase.table("users").select("*").eq("id", user_id).limit(1).execute()
    return res.data[0]


def list_last_jobs(tg_user_id: int, limit: int = 5) -> list[dict]:
    u = supabase.table("users").select("id").eq("tg_user_id", tg_user_id).limit(1).execute()
    if not u.data:
        return []
    user_id = u.data[0]["id"]

    r = (
        supabase.table("jobs")
        .select("id,kind,status,created_at,output_url,error,template_id")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return r.data or []
