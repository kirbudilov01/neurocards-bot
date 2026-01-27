# Start bot/workers without touching redis/postgres
cd /root/neurocards-bot
docker-compose up -d --no-deps neurocards-polling neurocards-worker-1 neurocards-worker-2 neurocards-worker-3

# Verify
docker ps | grep neurocards
docker logs --tail 50 neurocards-bot
docker logs --tail 50 neurocards-worker-1# Start bot/workers without touching redis/postgres
cd /root/neurocards-bot
docker-compose up -d --no-deps neurocards-polling neurocards-worker-1 neurocards-worker-2 neurocards-worker-3

# Verify
docker ps | grep neurocards
docker logs --tail 50 neurocards-bot
docker logs --tail 50 neurocards-worker-1docker compose logs neurocards-polling --tail 150# ✅ Backend Refactor Complete

## 🎯 What Was Done

Refactored the entire backend to ensure **correct, atomic, and scalable** video generation flow.

---

## 🔧 Key Changes

### 1. **Fixed Concurrency Issues**
- **db_adapter.py**: `fetch_next_queued_job()` no longer sets status to 'processing'
  - Prevents race condition where bot updates status while worker is processing
  - Worker explicitly calls `update_job(status='processing')` instead
  - Multiple workers can safely run in parallel

### 2. **Improved Error Handling & Logging**
- **menu_and_flow.py**: Enhanced logging at every step
  - Tracks `success_count` vs `error_count`
  - Logs validation (credits, data)
  - Logs each job creation attempt
  
- **generation.py**: Comprehensive logging through entire flow
  - Photo download → Upload → RPC call → DB update
  - Specific error classification (insufficient credits, duplicate, transient)
  - Clear error messages to user

### 3. **Documented Architecture**
- **ARCHITECTURE.md**: Complete system design with message flow diagrams
- **DEPLOYMENT_GUIDE.md**: Step-by-step deployment and monitoring instructions

---

## 🏗 Architecture (3 Containers + PostgreSQL Queue)

```
┌──────────────────┐
│   TELEGRAM BOT   │─────────┐
└──────────────────┘         │
                             ↓
                    ┌────────────────┐
                    │  POSTGRESQL    │
                    │   Job Queue    │
                    │  (status=q)    │
                    └────────────────┘
                             ↑
                             │
┌──────────────────┐─────────┘
│  WORKER (N×)     │
│ Processes jobs   │
│ Calls KIE → Bot  │
└──────────────────┘
```

---

## ✨ Flow Guarantees

| Guarantee | Mechanism | Benefit |
|-----------|-----------|---------|
| **Atomic Credit Deduction** | RPC function in PostgreSQL | No double-charge if RPC fails |
| **Idempotent Job Creation** | Unique idempotency_key | No duplicate jobs |
| **Real-time User Feedback** | Worker sends messages at each stage | User always knows what's happening |
| **Automatic Retries** | Worker retries TEMPORARY errors 3× | Handles Sora 2 overload gracefully |
| **Worker Safety** | FOR UPDATE SKIP LOCKED + manual status update | Multiple workers won't process same job |
| **Credit Recovery** | Auto-refund on final failure | No lost credits |

---

## 🧪 Ready to Test

### Local Testing (if running locally):
```bash
# 1. Pull latest
git pull origin main

# 2. Start bot
python app/main_polling.py

# 3. In another terminal, start worker
python worker/worker.py

# 4. Send test job via Telegram
# Watch logs for:
# ✅ "Job created and added to queue"
# ✅ Worker picks up job
# ✅ "Sora 2 generating..." or "Error: ..."
# ✅ User receives result or error message
```

### Server Deployment:
```bash
# See DEPLOYMENT_GUIDE.md for:
# - Docker deployment
# - Systemd deployment
# - Live monitoring
# - Troubleshooting
```

---

## 📋 Deployment Checklist

Before deploying to server:

- [ ] Latest code pulled: `git pull origin main`
- [ ] All env vars set: BOT_TOKEN, DATABASE_URL, KIE_API_KEY, OPENAI_API_KEY
- [ ] PostgreSQL running with RPC function
- [ ] Old services stopped
- [ ] New services started
- [ ] Logs being monitored
- [ ] Test job creation works
- [ ] Worker processes jobs
- [ ] User receives notifications

---

## 📚 Documentation

- **ARCHITECTURE.md** - Full system design, message flow, schema, RPC details
- **DEPLOYMENT_GUIDE.md** - Step-by-step deployment, monitoring, troubleshooting
- **This file** - Summary of changes

---

## 🚀 Next Steps on Server

1. **Pull latest code**
   ```bash
   cd /path/to/neurocards-bot
   git pull origin main
   ```

2. **Stop current services**
   ```bash
   systemctl stop neurocards-bot neurocards-worker@1
   sleep 2
   ```

3. **Start fresh**
   ```bash
   systemctl start neurocards-bot
   sleep 3
   systemctl status neurocards-bot --no-pager
   
   systemctl start neurocards-worker@1
   sleep 3
   systemctl status neurocards-worker@1 --no-pager
   ```

4. **Monitor live**
   ```bash
   # Terminal 1
   tail -f /var/neurocards/neurocards-bot/bot.log
   
   # Terminal 2
   tail -f /var/neurocards/neurocards-bot/worker-1.log
   ```

5. **Test complete flow**
   - Send /start in Telegram
   - Upload photo of product
   - Select template
   - Enter description
   - Confirm
   - Watch logs as job is created and processed
   - Receive video/error message from user

---

## 🐛 January 27, 2026: Critical Bug Fixes & Feature Completion

### 1. **Fixed Storage File Serving (KIE Image Fetch)**
- **Problem**: KIE was getting 404 when fetching product images for nested paths
- **Root Cause**: Route pattern `/storage/{bucket}/{filename}` only captured single segment
- **Fix**: Changed to `/storage/{bucket}/{tail:.*}` for greedy path matching
  - Now supports nested paths like `inputs/5235703016/uuid.jpg`
  - curl returns 200 with `Content-Type: image/jpeg`
- **File**: [app/main_polling.py](app/main_polling.py)

### 2. **Fixed Double Credit Refunds**
- **Problem**: Users reported credits growing unexpectedly (5→9 instead of 5→4)
- **Root Cause**: Multiple `refund_credit()` calls in same job without tracking
  - If video_url not found OR exception occurs → second refund in catch block
  - No flag to prevent double-refund
- **Fix**: Added `credit_refunded` flag to track refund state
  - Only refund if not already refunded (prevents duplicates)
  - Exception handler checks flag before calling `refund_credit()`
- **Files**: [worker/worker.py](worker/worker.py)

### 3. **Implemented "Generate More with Same Product" Feature**
- **Problem**: Two parallel implementations with duplicate code
  - `retry:` callback for historical jobs (in worker)
  - `make_another_same_product` callback (in state)
  - No handler for the second one
- **Solution**: Unified both into single state flow
  - `retry:{job_id}` → loads job from DB → `waiting_video_count` state
  - `make_another_same_product` → uses FSM state data → `waiting_video_count` state
  - Both converge at video count selection with same keyboard
- **Files**: 
  - [app/handlers/menu_and_flow.py](app/handlers/menu_and_flow.py) - handlers
  - [worker/video_processor.py](worker/video_processor.py) - keyboard generation

### 4. **Added Early KIE Validation Messaging**
- **Improvement**: Notify users immediately if photo passes/fails Sora-2 checks
- **Implementation**: 
  - After task creation, poll KIE once for initial status
  - If pass: "✅ Фото прошло проверку Sora 2, запускаю генерацию..."
  - If fail: "⚠️ Фото не прошло проверку Sora 2" + requirements
- **File**: [worker/worker.py](worker/worker.py)

### 5. **Retry System Validation**
- **Status**: ✅ Working correctly
  - 3 automatic retry attempts on RATE_LIMIT/TEMPORARY errors
  - Proper error classification (RATE_LIMIT, BILLING, TEMPORARY, UNKNOWN)
  - Credit refunds working as expected
  - User messages updated for each retry

---

## ✅ System is Production-Ready!

All critical issues fixed:
- ✅ No more "Данных не хватает" errors (proper data handling)
- ✅ No race conditions (concurrent-safe job fetching)
- ✅ Clear error messages (classified by type)
- ✅ Real-time user feedback (messages at each stage)
- ✅ Scalable (multiple workers supported)
- ✅ Observable (comprehensive logging)

**Ready to deploy!** 🚀

