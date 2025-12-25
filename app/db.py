from __future__ import annotations
from typing import Any, Dict, Optional, Tuple
from supabase import create_client, Client
from app.config import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY

supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

def get_or_create_user(tg_user_id: int, username: Optional[str] = None) -> Dict[str, Any]:
    res = supabase.table("users").select("*").eq("tg_user_id", tg_user_id).limit(1).execute()
    if res.data:
        # опционально обновим username
        if username and res.data[0].get("username") != username:
            supabase.table("users").update({"username": username}).eq("tg_user_id", tg_user_id).execute()
        return res.data[0]

    # новый пользователь (credits default = 10)
    ins = supabase.table("users").insert({
        "tg_user_id": tg_user_id,
        "username": username
    }).execute()
    return ins.data[0]

def create_job(
    tg_user_id: int,
    kind: str,  # "reels" | "neurocard"
    input_photo_path: str,
    product_info: Dict[str, Any],
    extra_wishes: str | None,
    template_id: str = "template_1",
) -> Dict[str, Any]:
    user = get_or_create_user(tg_user_id)
    res = supabase.table("jobs").insert({
        "user_id": user["id"],
        "kind": kind,
        "status": "queued",
        "template_id": template_id,
        "input_photo_path": input_photo_path,
        "product_info": product_info,
        "extra_wishes": extra_wishes,
    }).execute()
    return res.data[0]

def consume_credit(tg_user_id: int, job_id: str) -> int:
    """
    RPC public.consume_credit(p_tg_user_id bigint, p_job_id uuid) -> new_credits
    """
    res = supabase.rpc("consume_credit", {"p_tg_user_id": tg_user_id, "p_job_id": job_id}).execute()
    # supabase-py вернет list[{"new_credits": int}]
    return int(res.data[0]["new_credits"])

def get_user_by_id(user_id: str) -> Dict[str, Any]:
    res = supabase.table("users").select("*").eq("id", user_id).limit(1).execute()
    return res.data[0]

def update_job_status(job_id: str, status: str, **fields: Any) -> None:
    payload = {"status": status, **fields}
    supabase.table("jobs").update(payload).eq("id", job_id).execute()

def fetch_next_queued_job() -> Optional[Dict[str, Any]]:
    """
    MVP без SKIP LOCKED: берем самый ранний queued.
    Для одного воркера этого достаточно.
    """
    res = supabase.table("jobs").select("*").eq("status", "queued").order("created_at", desc=False).limit(1).execute()
    return res.data[0] if res.data else None
