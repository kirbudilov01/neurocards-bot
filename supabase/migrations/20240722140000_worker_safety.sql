-- Add columns to the jobs table for worker safety and observability.
ALTER TABLE public.jobs
ADD COLUMN attempt_count INT NOT NULL DEFAULT 0,
ADD COLUMN last_error TEXT,
ADD COLUMN failed_at TIMESTAMPTZ,
ADD COLUMN worker_id TEXT;

-- Create an index on the status column for faster querying of queued jobs.
CREATE INDEX idx_jobs_status ON public.jobs(status);

-- Create the RPC function to atomically claim the next available job.
CREATE OR REPLACE FUNCTION claim_next_job(p_worker_id TEXT)
RETURNS SETOF public.jobs
LANGUAGE plpgsql
AS $$
DECLARE
    v_job_id UUID;
BEGIN
    -- Atomically find and lock the next available job.
    SELECT id INTO v_job_id
    FROM public.jobs
    WHERE status = 'queued'
    ORDER BY created_at
    FOR UPDATE SKIP LOCKED
    LIMIT 1;

    -- If a job was found, update it with the worker ID and new status.
    IF v_job_id IS NOT NULL THEN
        RETURN QUERY
        UPDATE public.jobs
        SET
            status = 'processing',
            worker_id = p_worker_id,
            started_at = NOW()
        WHERE id = v_job_id
        RETURNING *;
    END IF;
END;
$$;
