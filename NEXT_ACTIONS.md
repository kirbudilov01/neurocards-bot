# 🎯 NEXT IMMEDIATE ACTIONS - Single Worker Strategy

## Current Status ✅
- All 3 critical credit DB functions deployed and tested
- All services (bot, workers, postgres, redis) running
- System ready for stabilization phase

## Issue: Multiple Bot Instances Polling
**Current:** There's another bot instance running and polling on Telegram  
**Fix Required:** Kill any old bot instances on VPS before testing

```bash
# SSH to VPS and check for running bot processes:
ps aux | grep "neurocards\|python.*main"

# Kill any old instances:
pkill -f "neurocards.*bot"
pkill -f "main_polling.py"
```

---

## Phase 1: Single Worker Stabilization (THIS WEEK)

### Step 1: Scale Docker Compose to 1 Worker
Edit `docker-compose.yml`:
```yaml
# Remove these sections:
# - neurocards-worker-2
# - neurocards-worker-3

# Keep only:
services:
  neurocards-worker-1:
    # ... single worker config
```

Then:
```bash
docker-compose down
docker-compose up -d
```

### Step 2: Run 50+ Test Cycles
```bash
# Monitor worker logs:
docker-compose logs -f neurocards-worker-1

# Send photos to bot through Telegram
# Check each job:
# 1) Photo uploaded ✓
# 2) Job created (1 credit deducted) ✓
# 3) KIE.AI task created ✓
# 4) Polling starts (see detailed logs) ✓
# 5) Video completed OR error ✓
# 6) If error → credit refunded ✓
```

### Step 3: Verification Checklist
```
☐ No jobs stuck > 15 minutes
☐ All credits properly accounted for
☐ All operations logged to credits_history
☐ Worker restarts cleanly if crashed
☐ Error messages clear to user
☐ Timeout handling works
```

---

## Phase 2: Payment System (NEXT WEEK)

### Implement Topup Handler
Location: `app/handlers/menu_and_flow.py`

```python
async def topup_handler(callback_query: CallbackQuery, state: FSMContext):
    """Show pricing plans and handle topup"""
    
    plans = [
        ("Стартер", 5, 199),     # 5 credits for 199 RUB
        ("Профи", 20, 699),      # 20 credits for 699 RUB
        ("Премиум", 50, 1499),   # 50 credits for 1499 RUB
    ]
    
    # Show inline buttons for each plan
    # On selection → create payment via YooKassa
    # Generate payment link
    # Wait for webhook notification
    # Call complete_payment() to add credits
    # Send confirmation
```

### Payment Webhook Handler
```python
async def payment_webhook(request: web.Request):
    """Handle payment notification from YooKassa"""
    data = await request.json()
    
    # Verify signature
    # Get payment_id, status, amount
    # If status == 'succeeded':
    #   - Calculate credits from amount
    #   - Call complete_payment(payment_id, tg_user_id, credits)
    #   - Send notification to user
```

---

## Quick Reference: Credit Functions

```sql
-- Add credits (for topup, bonus)
SELECT add_credits(tg_user_id, 10, 'topup');
-- Returns: new_balance

-- Refund credit (on job failure)
SELECT refund_credit(tg_user_id);
-- Returns: new_balance (current + 1)

-- Complete payment (on payment webhook)
SELECT complete_payment(payment_id, tg_user_id, 10);
-- Returns: {"success": true, "new_credits": N}
```

---

## Critical Files to Monitor

| File | What to Watch |
|------|---|
| `worker/video_processor.py` | KIE polling status, error messages |
| `worker/kie_client.py` | Task creation, status responses |
| `app/db_adapter.py` | Credit operations |
| `app/handlers/menu_and_flow.py` | User interactions, topup |
| Docker logs | Overall health, errors |

---

## Debug Commands

```bash
# Check current user credits
docker-compose exec postgres psql -U neurocards -d neurocards -c \
  "SELECT tg_user_id, credits FROM users WHERE tg_user_id = 5235703016;"

# View credits history for user
docker-compose exec postgres psql -U neurocards -d neurocards -c \
  "SELECT amount, operation_type FROM credits_history WHERE tg_user_id = 5235703016 ORDER BY created_at DESC LIMIT 10;"

# View recent jobs
docker-compose exec postgres psql -U neurocards -d neurocards -c \
  "SELECT id, status, error_message FROM jobs ORDER BY created_at DESC LIMIT 10;"

# Check Redis queue size
docker-compose exec redis redis-cli LLEN "rq:queue:neurocards"

# View worker status
docker-compose logs neurocards-worker-1 | grep -E "Listening|Processing|completed|failed"
```

---

## Success Criteria

✅ System is **stabilized on single worker**  
✅ 50+ cycles run **with zero stuck jobs**  
✅ Credits are **properly refunded on errors**  
✅ All operations **logged to audit trail**  
✅ **Ready for payment system** implementation  

---

**Next: Kill other bot instances on VPS, then switch to single worker mode.**
