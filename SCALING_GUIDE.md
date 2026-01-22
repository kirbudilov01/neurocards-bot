# 🚀 Scaling Guide - Neurocards Bot

Quick reference for scaling the bot infrastructure.

---

## 📊 Current Setup

- **Workers:** 20 instances
- **Capacity:** ~4,800 videos/day
- **Database:** PostgreSQL with optimized schema
- **API Keys:** Rotator ready (currently 1 key)

---

## ⚡ Quick Scale Commands

### Add More Workers (e.g., to 50 total)

```bash
# SSH to VPS
ssh root@185.93.108.162

# Start workers 21-50
for i in {21..50}; do
  systemctl enable neurocards-worker@$i
  systemctl start neurocards-worker@$i
done

# Check status
systemctl status 'neurocards-worker@*' | grep "Active: active" | wc -l
```

### Stop Extra Workers

```bash
# Stop workers 21-50
for i in {21..50}; do
  systemctl stop neurocards-worker@$i
  systemctl disable neurocards-worker@$i
done
```

### Using Management Script

```bash
# Set desired count
export WORKER_INSTANCES=50

# Restart all
cd /var/neurocards/neurocards-bot
./scripts/manage_workers.sh restart

# Check status
./scripts/manage_workers.sh status
```

---

## 🔑 Add More KIE API Keys

### 1. Edit .env file

```bash
ssh root@185.93.108.162
nano /var/neurocards/neurocards-bot/.env
```

### 2. Add keys

```bash
# Keep existing
KIE_API_KEY=your_first_key

# Add more
KIE_API_KEY_1=your_first_key
KIE_API_KEY_2=your_second_key
KIE_API_KEY_3=your_third_key
KIE_API_KEY_4=your_fourth_key
# ... and so on
```

### 3. Restart workers

```bash
systemctl restart 'neurocards-worker@*'
```

**Note:** Keys will be automatically rotated round-robin. If a key hits rate limit, it's automatically blocked for 60 minutes.

---

## 📈 Monitoring

### Check Queue Status

```bash
# Via database
ssh root@185.93.108.162 "sudo -u postgres psql -d neurocards -c \"
  SELECT status, COUNT(*) 
  FROM jobs 
  WHERE created_at > NOW() - INTERVAL '1 hour'
  GROUP BY status;
\""
```

### Check Worker Health

```bash
# Count running workers
ssh root@185.93.108.162 "systemctl is-active 'neurocards-worker@*' | grep -c 'active'"

# View logs from all workers
ssh root@185.93.108.162 "tail -f /var/log/syslog | grep neurocards-worker"

# View logs from specific worker
ssh root@185.93.108.162 "grep 'neurocards-worker-5' /var/log/syslog | tail -50"
```

### Check API Key Health

Workers automatically log API key issues:
```bash
ssh root@185.93.108.162 "grep 'rate limited\|billing error' /var/log/syslog | tail -20"
```

---

## 🎯 When to Scale

### Indicators to ADD workers:

1. **Queue growing:**
   - `queued` count > 100 jobs → Add +10 workers
   - `queued` count > 500 jobs → Add +20 workers

2. **Long wait times:**
   - Average wait > 15 min → Add +10 workers
   - Average wait > 30 min → Add +20 workers

3. **Peak hours traffic:**
   - 20:00-22:00 MSK sees 2x traffic → Pre-scale before peak

### Indicators to REDUCE workers:

1. **Low utilization:**
   - `queued` count = 0 for > 1 hour → Reduce by 50%
   - Most workers idle → Keep only 5-10 for base load

2. **Cost optimization:**
   - Off-peak hours (02:00-06:00 MSK) → Reduce to 5 workers

---

## 💰 Cost Optimization

### Strategy 1: Dynamic Scaling

Create cron jobs for peak/off-peak:

```bash
# Peak hours (19:00-23:00 MSK) - 50 workers
0 16 * * * cd /var/neurocards/neurocards-bot && WORKER_INSTANCES=50 ./scripts/manage_workers.sh restart

# Off-peak (01:00-07:00 MSK) - 5 workers  
0 22 * * * cd /var/neurocards/neurocards-bot && WORKER_INSTANCES=5 ./scripts/manage_workers.sh restart

# Normal hours - 20 workers
0 4 * * * cd /var/neurocards/neurocards-bot && WORKER_INSTANCES=20 ./scripts/manage_workers.sh restart
```

### Strategy 2: Queue-Based Auto-Scale

Add monitoring script:

```bash
#!/bin/bash
# /var/neurocards/autoscale.sh

QUEUED=$(sudo -u postgres psql -d neurocards -t -c "SELECT COUNT(*) FROM jobs WHERE status='queued';")
CURRENT=$(systemctl is-active 'neurocards-worker@*' | grep -c 'active')

if [ "$QUEUED" -gt 200 ] && [ "$CURRENT" -lt 50 ]; then
  # Scale up
  cd /var/neurocards/neurocards-bot
  WORKER_INSTANCES=50 ./scripts/manage_workers.sh restart
elif [ "$QUEUED" -lt 10 ] && [ "$CURRENT" -gt 10 ]; then
  # Scale down
  cd /var/neurocards/neurocards-bot
  WORKER_INSTANCES=10 ./scripts/manage_workers.sh restart
fi
```

Run every 5 minutes:
```bash
*/5 * * * * /var/neurocards/autoscale.sh
```

---

## 🚨 Emergency Procedures

### All Workers Stuck

```bash
# Kill all workers
systemctl stop 'neurocards-worker@*'

# Reset stuck jobs in database
sudo -u postgres psql -d neurocards -c "
  UPDATE jobs 
  SET status='queued' 
  WHERE status='processing' 
  AND started_at < NOW() - INTERVAL '30 minutes';
"

# Restart workers
systemctl start 'neurocards-worker@*'
```

### Database Connection Issues

```bash
# Check PostgreSQL status
systemctl status postgresql

# Restart if needed
systemctl restart postgresql

# Restart all workers after DB restart
systemctl restart 'neurocards-worker@*'
```

### KIE API All Keys Blocked

```bash
# Check which keys are blocked (look for "blocked" in logs)
grep "KIE API key" /var/log/syslog | tail -50

# Wait for cooldown (60 min for rate limit)
# OR add new keys to .env

# Force unblock all keys (restart workers)
systemctl restart 'neurocards-worker@*'
```

---

## 📊 Capacity Planning

### Current (20 workers):
- **Daily:** 4,800 videos
- **Peak 2h:** 400 videos
- **Per Worker:** ~240 videos/day

### With 50 workers:
- **Daily:** 12,000 videos
- **Peak 2h:** 1,000 videos
- **Good for:** Up to 5M user base

### With 100 workers:
- **Daily:** 24,000 videos
- **Peak 2h:** 2,000 videos
- **Good for:** 10M+ user base

---

## 🔧 Maintenance

### Weekly Tasks:
```bash
# Check disk space
df -h

# Clean old logs (keep last 7 days)
journalctl --vacuum-time=7d

# Check failed jobs
sudo -u postgres psql -d neurocards -c "
  SELECT COUNT(*), error 
  FROM jobs 
  WHERE status='failed' AND created_at > NOW() - INTERVAL '7 days'
  GROUP BY error;
"
```

### Monthly Tasks:
```bash
# Analyze database performance
sudo -u postgres psql -d neurocards -c "VACUUM ANALYZE;"

# Review worker count vs actual usage
# Adjust base count if needed
```

---

## 📞 Support

- **Telegram:** @kirbudilov
- **Logs:** `/var/log/syslog` or `journalctl`
- **Database:** `sudo -u postgres psql -d neurocards`
- **Workers:** `systemctl status 'neurocards-worker@*'`

---

**Remember:** More workers = more videos/day, but also more server load. Scale based on actual demand!
