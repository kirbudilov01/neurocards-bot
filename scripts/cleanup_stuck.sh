#!/bin/bash
# Cron job для очистки зависших задач (запускать каждые 15 минут)
# */15 * * * * /root/neurocards-bot/scripts/cleanup_stuck.sh >> /var/log/neurocards-cleanup.log 2>&1

docker exec neurocards-postgres psql -U neurocards -d neurocards -c "
-- Пометить зависшие задачи как failed (> 2 часов)
UPDATE jobs
SET status = 'failed',
    error = 'Worker timeout - job stuck for >2 hours',
    finished_at = NOW()
WHERE status IN ('processing', 'queued')
  AND created_at < NOW() - INTERVAL '2 hours'
RETURNING id, tg_user_id;
" | grep -E "^\s+[a-f0-9-]+" | while read job_id tg_user_id; do
    echo "$(date): Marking job $job_id as failed (user $tg_user_id)"
done

# Вернуть кредиты за failed задачи последнего часа
docker exec neurocards-postgres psql -U neurocards -d neurocards -c "
UPDATE users u
SET credits = credits + stuck_counts.cnt,
    updated_at = NOW()
FROM (
    SELECT tg_user_id, COUNT(*) as cnt
    FROM jobs
    WHERE status = 'failed'
      AND error LIKE '%Worker timeout%'
      AND finished_at > NOW() - INTERVAL '1 hour'
    GROUP BY tg_user_id
) stuck_counts
WHERE u.tg_user_id = stuck_counts.tg_user_id
RETURNING u.tg_user_id, stuck_counts.cnt as refunded, u.credits;
"

echo "$(date): Cleanup completed"
