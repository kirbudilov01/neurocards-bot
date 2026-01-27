# 🚀 Server Deployment Guide

## ✅ What's Ready

The backend is now **fully functional and production-ready**:

- ✅ **Atomic job creation**: RPC ensures credits deducted iff job created
- ✅ **Proper error handling**: All errors classified (TEMPORARY, RATE_LIMIT, USER_VIOLATION)
- ✅ **Worker concurrency**: Multiple workers can safely process jobs
- ✅ **Real-time user feedback**: Messages at every stage (start, retry, complete, fail)
- ✅ **Comprehensive logging**: Every step traced in logs
- ✅ **No race conditions**: FOR UPDATE SKIP LOCKED + atomic RPC

---

## 📋 Pre-deployment Checklist

Before starting containers, verify:

```bash
# 1. Environment variables are set
echo $BOT_TOKEN
echo $DATABASE_URL
echo $KIE_API_KEY
echo $OPENAI_API_KEY

# 2. PostgreSQL is running and schema is up-to-date
psql $DATABASE_URL -c "SELECT count(*) FROM jobs;"
psql $DATABASE_URL -c "\df create_job_and_consume_credit"  # RPC exists?

# 3. Latest code is pulled
cd /path/to/neurocards-bot
git pull origin main
```

---

## 🐳 Deploy with Docker (Recommended)

### Step 1: Build Images
```bash
cd /path/to/neurocards-bot

# Build bot image
docker build -f Dockerfile.bot -t neurocards-bot:latest .

# Build worker image
docker build -f Dockerfile.worker -t neurocards-worker:latest .
```

### Step 2: Start Services
```bash
# Start all containers
docker-compose -f docker-compose.yml up -d

# Verify services started
docker ps | grep neurocards
docker logs neurocards-bot --tail 50
docker logs neurocards-worker-1 --tail 50
```

### Step 3: Monitor Live
```bash
# Terminal 1: Bot logs
docker logs -f neurocards-bot

# Terminal 2: Worker logs
docker logs -f neurocards-worker-1

# Terminal 3: Query database
watch -n 2 "psql $DATABASE_URL -c \"
  SELECT 
    status, 
    COUNT(*) as count 
  FROM jobs 
  WHERE created_at > now() - interval '1 hour' 
  GROUP BY status 
  ORDER BY status;\""
```

---

## 🖥️ Deploy with Systemd (If Not Using Docker)

### Step 1: Pull Latest Code
```bash
cd /path/to/neurocards-bot
git fetch origin
git reset --hard origin/main
```

### Step 2: Install Dependencies
```bash
# Create virtualenv if not exists
python3 -m venv .venv
source .venv/bin/activate

# Install requirements
pip install -r requirements.txt --upgrade
```

### Step 3: Stop Old Services
```bash
systemctl stop neurocards-bot
systemctl stop neurocards-worker@1
sleep 2
```

### Step 4: Start Services
```bash
# Start bot
systemctl start neurocards-bot
sleep 3
systemctl status neurocards-bot --no-pager

# Start worker
systemctl start neurocards-worker@1
sleep 3
systemctl status neurocards-worker@1 --no-pager
```

### Step 5: Monitor Logs
```bash
# In separate terminals:
tail -f /var/neurocards/neurocards-bot/bot.log
tail -f /var/neurocards/neurocards-bot/worker-1.log

# OR use journalctl:
journalctl -u neurocards-bot -f
journalctl -u neurocards-worker@1 -f
```

---

## 🧪 Test End-to-End

### Test 1: Job Creation Flow
```python
# Send via Telegram:
1. /start
2. Send photo of product
3. Select template (UGC, AD, etc.)
4. Enter description (e.g., "красивая сумка синяя")
5. Optionally add wishes
6. Confirm

# Expected:
✅ "✅ Принял! 1 видео запущена"
✅ Check logs: "Job created and added to PostgreSQL queue"
```

### Test 2: Worker Processing
```bash
# Watch worker logs while test 1 happens:
tail -f /var/neurocards/neurocards-bot/worker-1.log

# Expected to see:
📦 START generate: user=123456, template=ugc, kind=reels
📝 RPC call: create_job_and_consume_credit
✅ RPC result: job_id=..., credits=49
💼 Processing job ...
🎬 Generating script with GPT
📤 Creating KIE task
⏳ Polling KIE for task ...
[after 1-30 min]
✅ Video ready or ❌ Error: ...
```

### Test 3: Error Handling
```bash
# Insufficient credits:
- User has < 1 credit
- Try to generate
- Expected: "❌ Недостаточно кредитов. Нужно: 1, У вас: 0"

# Duplicate job:
- Send 2 identical jobs from same callback
- Expected: 2nd returns existing job_id (idempotency works)

# KIE Error (Sora 2 overload):
- Will auto-retry 3 times with "⏳ Sora 2 перегружена..."
- If still fails: "❌ Sora 2 не может обработать. 1 кредит вернулся ✅"
```

---

## 📊 Monitor System Health

### Database Queries

```sql
-- Active jobs
SELECT 
  status, 
  COUNT(*) as count,
  AVG(EXTRACT(EPOCH FROM (finished_at - created_at))) as avg_duration_sec
FROM jobs
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY status;

-- Recent failures
SELECT id, tg_user_id, error, finished_at
FROM jobs
WHERE status = 'failed' 
  AND finished_at > NOW() - INTERVAL '1 hour'
ORDER BY finished_at DESC
LIMIT 10;

-- Stuck jobs (processing > 30 min)
SELECT id, tg_user_id, created_at, started_at
FROM jobs
WHERE status = 'processing'
  AND started_at < NOW() - INTERVAL '30 minutes'
ORDER BY created_at ASC;

-- Queue depth
SELECT COUNT(*) as queued_jobs FROM jobs WHERE status = 'queued';
```

### Systemd Health Checks

```bash
# Bot service health
systemctl is-active neurocards-bot
systemctl show neurocards-bot -p MainPID

# Worker service health
systemctl is-active neurocards-worker@1
systemctl show neurocards-worker@1 -p MainPID

# Restart if needed
systemctl restart neurocards-bot
systemctl restart neurocards-worker@1
```

---

## 🔧 Troubleshooting

### Bot Won't Start
```bash
systemctl status neurocards-bot
journalctl -u neurocards-bot -n 50 --no-pager

# Common issues:
# - BOT_TOKEN missing or invalid
# - DATABASE_URL incorrect (can't connect)
# - Port already in use (if using API mode)
```

### Worker Won't Process Jobs
```bash
systemctl status neurocards-worker@1
journalctl -u neurocards-worker@1 -n 50 --no-pager

# Common issues:
# - DATABASE_URL incorrect (can't connect)
# - KIE_API_KEY invalid or expired
# - OPENAI_API_KEY missing
# - Process stuck (check: ps aux | grep worker)
```

### Stuck Jobs (processing > 30 min)
```bash
# Option 1: Restart worker (will pick up the job again)
systemctl restart neurocards-worker@1

# Option 2: Mark as failed and refund credit
psql $DATABASE_URL -c "
  UPDATE jobs 
  SET status='failed', error='timeout_30min', finished_at=NOW()
  WHERE id='<job_id>' AND status='processing';
  
  UPDATE users 
  SET credits = credits + 1 
  WHERE tg_user_id=<tg_user_id>;
"
```

### KIE Rate Limit (429 errors)
```bash
# Check API key rotation
grep "RATE_LIMIT" /var/neurocards/neurocards-bot/worker-1.log

# Solution: Add more API keys to KIE_API_KEYS env var
export KIE_API_KEYS="key1,key2,key3,key4"
# Then restart worker
systemctl restart neurocards-worker@1
```

---

## 📈 Scaling Workers

To handle more jobs simultaneously:

```bash
# Scale to 3 workers
systemctl start neurocards-worker@1
systemctl start neurocards-worker@2
systemctl start neurocards-worker@3

# Check they're running
systemctl status neurocards-worker@{1,2,3} --no-pager

# Monitor
journalctl -u neurocards-worker@\* -f
```

---

## 🔐 Security Notes

- ✅ Never commit `.env` to git
- ✅ API keys rotated automatically in worker
- ✅ Database connections use connection pooling
- ✅ User messages sanitized before sending
- ✅ Job queue protected with FOR UPDATE SKIP LOCKED

---

## ✅ You're Ready!

The system is now ready for production:
1. Pull the latest code: `git pull origin main`
2. Deploy using Docker or Systemd
3. Test end-to-end flow
4. Monitor logs in real-time
5. Scale workers as needed

Good luck! 🚀

