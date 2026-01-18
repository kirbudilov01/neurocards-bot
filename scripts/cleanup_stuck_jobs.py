"""
Утилита для очистки зависших задач.
Можно запустить как cron job или вручную для отладки.
"""

import os
import sys
from datetime import datetime, timezone, timedelta
from supabase import create_client


def cleanup_stuck_jobs():
    """
    Находит задачи, которые застряли в статусе 'processing' более 15 минут
    и возвращает их в 'queued' или помечает как 'failed'.
    """
    
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    
    if not supabase_url or not supabase_key:
        print("❌ Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")
        return
    
    supabase = create_client(supabase_url, supabase_key)
    
    # Время 15 минут назад
    threshold = datetime.now(timezone.utc) - timedelta(minutes=15)
    threshold_iso = threshold.isoformat()
    
    print(f"🔍 Searching for stuck jobs (processing since before {threshold_iso})...")
    
    # Найти все задачи в processing старше 15 минут
    result = supabase.table("jobs").select("*").eq("status", "processing").lt("started_at", threshold_iso).execute()
    
    stuck_jobs = result.data or []
    
    if not stuck_jobs:
        print("✅ No stuck jobs found")
        return
    
    print(f"⚠️ Found {len(stuck_jobs)} stuck job(s)")
    
    for job in stuck_jobs:
        job_id = job["id"]
        attempts = job.get("attempts", 0)
        max_attempts = 3
        
        if attempts >= max_attempts:
            # Слишком много попыток - помечаем как failed
            print(f"❌ Job {job_id}: max attempts reached ({attempts}), marking as failed")
            supabase.table("jobs").update({
                "status": "failed",
                "error": f"stuck_after_{attempts}_attempts",
                "finished_at": datetime.now(timezone.utc).isoformat()
            }).eq("id", job_id).execute()
            
            # Возвращаем кредит
            user_id = job.get("user_id")
            if user_id:
                user = supabase.table("users").select("tg_user_id").eq("id", user_id).limit(1).execute()
                if user.data:
                    tg_user_id = user.data[0]["tg_user_id"]
                    supabase.rpc("refund_credit", {"p_tg_user_id": tg_user_id, "p_amount": 1}).execute()
                    print(f"  ↩️ Refunded 1 credit to user {tg_user_id}")
        else:
            # Вернуть в очередь для повторной попытки
            print(f"🔄 Job {job_id}: resetting to queued (attempt {attempts}/{max_attempts})")
            supabase.table("jobs").update({
                "status": "queued",
                "started_at": None,
            }).eq("id", job_id).execute()
    
    print("✅ Cleanup complete")


if __name__ == "__main__":
    cleanup_stuck_jobs()
