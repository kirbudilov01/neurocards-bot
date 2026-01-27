# 🏗 Архитектура системы Neurocards Bot

## Обзор

Система состоит из **3 независимых контейнеров** + **1 очередь в БД**:

```
┌─────────────────────────────────────────────────────────────────┐
│                        TELEGRAM BOT (aiogram)                   │
│  - Polling mode (без proxy, 180s timeout)                       │
│  - Handlers: /start, photo, template selection, wishes, confirm │
│  - Creates jobs atomically via RPC                              │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│                  PostgreSQL (Primary Queue)                      │
│  - jobs table: status={queued, processing, completed, failed}   │
│  - RPC: create_job_and_consume_credit() [atomic]                │
│  - JSONB: error_details, metadata                               │
│  - Polling: FOR UPDATE SKIP LOCKED                              │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ↓ (Worker polls jobs with status='queued')
┌─────────────────────────────────────────────────────────────────┐
│                    WORKER (rq_worker.py)                         │
│  - Fetches queued jobs                                          │
│  - Builds script via OpenAI (with GPT fallback)                 │
│  - Creates KIE task → Polls 15s intervals                       │
│  - Retry logic: 3 attempts, exponential backoff                 │
│  - Sends user messages on each state change                     │
│  - Updates job status → Sends result to user                    │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ├─→ COMPLETED: send_video() → update status
                         ├─→ FAILED: refund_credit → send error → update status
                         └─→ RETRY: return to queued → sleep → next loop
                         │
                         ↓ (Worker → User messages)
                        BOT (send_message/send_video)
                         │
                         ↓
                      TELEGRAM USER
```

---

## 🔄 Message Flow (Полный цикл)

### 1. **Job Creation** (Bot → Backend)
```
User: [sends photo] → [selects template] → [enters wishes] → [confirms]
                                                                 │
                                                                 ↓
Bot.handlers.menu_and_flow.confirm_generation()
  ├─ Validates: photo_file_id ✓, product_text ✓, credits ≥ video_count ✓
  ├─ For each video (i = 0 to video_count-1):
  │   ├─ Calls: generation.start_generation()
  │   │   ├─ Checks idempotency_key (no duplicates)
  │   │   ├─ Downloads photo from Telegram → Storage
  │   │   ├─ RPC: create_job_and_consume_credit() [ATOMIC]
  │   │   │   └─ Creates job + deducts 1 credit in single transaction
  │   │   ├─ Updates job: status='queued', metadata
  │   │   └─ Returns: (job_id, new_credits) or (None, None) on error
  │   └─ If job_id: success_count++
  │
  └─ If success_count > 0:
      └─ Sends: "✅ Принял! N видео запущена"

      If success_count == 0:
      └─ Sends: error message (handled by generation.start_generation)
```

**Key Points:**
- ✅ Credit deduction happens **inside RPC** (atomic)
- ✅ If RPC fails, NO credit deducted
- ✅ If RPC succeeds, job is **immediately in queue**
- ⚠️ Do NOT send success confirmation until after success_count check

---

### 2. **Job Processing** (Backend → Worker → KIE → Backend → User)
```
Worker.main_loop():
  While not shutdown:
    job = fetch_next_queued_job()  [FOR UPDATE SKIP LOCKED]
    
    If not job:
      sleep(2) → continue
    
    # ===== JOB FOUND =====
    attempts++ → update_job(status='processing')
    
    # 1. GET PROMPT
    script = build_script_for_job()  [GPT or fallback template]
    
    # 2. CREATE KIE TASK
    (task_id, api_key) = create_task_sora_i2v(prompt=script, image_url=image_url)
    update_job(kie_task_id=task_id)
    
    # 3. SEND USER: "🎬 Генерация запущена"
    send_message(user_id, "🎬 Генерация запущена!...")
    
    # 4. POLL KIE (15s intervals, 30min timeout)
    info = poll_record_info(task_id, timeout=1800, interval=15)
    
    # 5. HANDLE RESULT
    
    If FAIL:
      ├─ Classify error: TEMPORARY | RATE_LIMIT | USER_VIOLATION | UNKNOWN
      │
      ├─ If TEMPORARY or RATE_LIMIT and attempts < 3:
      │   ├─ Send: "⏳ Sora 2 перегружена, попытка N из 3..."
      │   ├─ Update: status='queued', attempts=N
      │   ├─ Sleep(retry_delay)
      │   └─ continue → next loop (fetch same job again)
      │
      └─ Else (final fail or USER_VIOLATION):
          ├─ refund_credit(user_id)  [1 credit back]
          ├─ update_job(status='failed', error=msg)
          ├─ Send: user_error_message(error_type)
          └─ sleep(1) → continue
    
    If SUCCESS:
      ├─ Download video from KIE → storage
      ├─ Update: status='completed', video_url=url
      ├─ Send: video or link to user
      └─ Log: "✅ Job completed"
    
    If EXCEPTION during processing:
      ├─ refund_credit(user_id)
      ├─ update_job(status='failed', error=str(e))
      ├─ Send: generic error message
      └─ continue with error counting
```

**Key Points:**
- ✅ Worker polls 15s apart (not overwhelming KIE)
- ✅ 3 retry attempts with exponential backoff
- ✅ User gets **real-time messages** during processing
- ✅ Credit refunded on final failure
- ✅ Job status always reflects reality
- ⚠️ Worker NEVER blocks bot (completely async)

---

## 🗄️ Database Schema (Critical columns)

```sql
-- jobs table
id                UUID PRIMARY KEY
tg_user_id        BIGINT
product_name      TEXT              -- product description (short)
product_text      TEXT              -- full product details
product_image_url TEXT              -- S3 path
extra_wishes      TEXT              -- user notes
idempotency_key   TEXT UNIQUE       -- prevent duplicates
prompt            TEXT              -- final GPT-built script
kie_task_id       TEXT              -- task ID from KIE API
kie_api_key       TEXT              -- which API key was used
status            TEXT              -- queued|processing|completed|failed
error             TEXT              -- error message (if failed)
error_details     JSONB             -- {template_id, kind, user_prompt}
attempts          INT               -- retry counter
video_url         TEXT              -- result video URL
created_at        TIMESTAMP
started_at        TIMESTAMP
finished_at       TIMESTAMP

-- CRITICAL RPC
CREATE OR REPLACE FUNCTION create_job_and_consume_credit(
  p_tg_user_id BIGINT,
  p_template_type TEXT,
  p_idempotency_key TEXT,
  p_photo_path TEXT,
  p_prompt_input JSONB
) RETURNS TABLE(job_id UUID, new_credits INT)
AS $$
  -- 1. Check if already exists (idempotency)
  -- 2. Check if user has credits
  -- 3. Create job with status='queued'
  -- 4. Deduct 1 credit from user
  -- 5. Return (job_id, new_credits)
  -- ALL IN ONE TRANSACTION - no race conditions!
$$
```

---

## 🔐 Error Handling Strategy

### Classification (KIE errors)

| Error Type | Cause | Action |
|-----------|-------|--------|
| **TEMPORARY** | HTTP 5xx, timeout | Retry (exp backoff) |
| **RATE_LIMIT** | HTTP 429, key limited | New API key + retry |
| **USER_VIOLATION** | Invalid prompt, image | FAIL + refund credit |
| **UNKNOWN** | Unexpected error | FAIL + refund credit |

### User Messages
```
┌─ On Retry:
│  "⏳ Sora 2 перегружена. Пробуем снова (попытка N/3)..."
│
├─ On Final Fail (Sora 2):
│  "❌ Sora 2 не может обработать. 1 кредит вернулся на баланс ✅"
│
├─ On Final Fail (User violation):
│  "❌ Не получилось с данной картинкой/описанием. 1 кредит вернулся ✅"
│
└─ On Success:
   "[video or link] ✅ Видео готово!"
```

---

## 🚀 Deployment Checklist

### Before starting:
- [ ] `.env` has: BOT_TOKEN, DATABASE_URL, KIE_API_KEY, OPENAI_API_KEY
- [ ] PostgreSQL running with schema + RPC function
- [ ] Redis running (for health checks, not primary queue)
- [ ] S3/Storage configured

### Start Services (in order):
```bash
# 1. Database migrations
# (already applied)

# 2. Start bot (polling)
systemctl start neurocards-bot
sleep 2
systemctl status neurocards-bot

# 3. Start worker (begins processing jobs)
systemctl start neurocards-worker@1
sleep 2
systemctl status neurocards-worker@1

# 4. Verify connectivity
journalctl -u neurocards-bot -f &
journalctl -u neurocards-worker@1 -f
```

### Monitoring:
```bash
# Bot logs
tail -f /var/neurocards/neurocards-bot/bot.log

# Worker logs
tail -f /var/neurocards/neurocards-bot/worker-1.log

# Queries:
select count(*) from jobs where status='queued';
select count(*) from jobs where status='processing';
```

---

## 🔧 Troubleshooting

### "⚠️ Данные не хватает"
- Check: photo_file_id, product_text not empty
- Solution: User must upload photo + enter description again

### "❌ Недостаточно кредитов"
- Check: `SELECT credits FROM users WHERE tg_user_id=X;`
- Solution: User must buy credits first

### "⏳ Sora 2 перегружена" (repeated)
- Check: API key rate limits not exceeded
- Check: KIE service status (kie.ai)
- Solution: Rotate API key or wait

### Job stuck in "processing" for 30+ min
- Check: Worker process running? `systemctl status neurocards-worker@1`
- Check: Logs for KIE timeout errors
- Solution: Manual: `UPDATE jobs SET status='failed', error='timeout' WHERE id=X;`

---

## 📊 Architecture Benefits

✅ **Decoupled**: Bot ≠ Worker ≠ Database (easy to scale)
✅ **Fault-tolerant**: Job queue persists if worker crashes
✅ **User-friendly**: Real-time notifications during processing
✅ **Atomic**: Credit deduction never races with job creation
✅ **Retry-able**: TEMPORARY errors auto-retry with backoff
✅ **Observable**: Every step logged with timestamps + error details

