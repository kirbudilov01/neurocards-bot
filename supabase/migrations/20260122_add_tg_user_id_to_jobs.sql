-- Migration: Add tg_user_id to jobs table for faster worker access
-- This eliminates the need for JOIN with users table in worker queries

-- 1. Add tg_user_id column to jobs
ALTER TABLE public.jobs ADD COLUMN IF NOT EXISTS tg_user_id BIGINT;

-- 2. Populate existing rows with tg_user_id from users table
UPDATE public.jobs j
SET tg_user_id = u.tg_user_id
FROM public.users u
WHERE j.user_id = u.id AND j.tg_user_id IS NULL;

-- 3. Make tg_user_id NOT NULL after backfill
ALTER TABLE public.jobs ALTER COLUMN tg_user_id SET NOT NULL;

-- 4. Add index for fast lookups
CREATE INDEX IF NOT EXISTS idx_jobs_tg_user_id ON public.jobs(tg_user_id);

-- 5. Update create_job_and_consume_credit function to include tg_user_id
CREATE OR REPLACE FUNCTION create_job_and_consume_credit(
    p_tg_user_id BIGINT,
    p_idempotency_key TEXT,
    p_kind TEXT,
    p_input_photo_path TEXT,
    p_product_info JSONB,
    p_extra_wishes TEXT,
    p_template_id TEXT
)
RETURNS TABLE(job_id UUID, new_credits INT)
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_job_id UUID;
    v_existing_job_id UUID;
    v_user_id UUID;
    v_user_credits INT;
    v_new_credits INT;
BEGIN
    -- 1. Check for existing job with same idempotency key
    SELECT id INTO v_existing_job_id FROM public.jobs WHERE idempotency_key = p_idempotency_key;
    IF v_existing_job_id IS NOT NULL THEN
        -- Job exists, return it with current credits
        SELECT credits INTO v_new_credits FROM public.users WHERE tg_user_id = p_tg_user_id;
        RETURN QUERY SELECT v_existing_job_id, COALESCE(v_new_credits, 0);
        RETURN;
    END IF;

    -- 2. Get user and lock row
    SELECT id, credits INTO v_user_id, v_user_credits 
    FROM public.users 
    WHERE tg_user_id = p_tg_user_id 
    FOR UPDATE;

    -- 3. Validate user exists
    IF v_user_id IS NULL THEN
        RAISE EXCEPTION 'User with tg_user_id % not found', p_tg_user_id;
    END IF;

    -- 4. Check credits
    IF v_user_credits IS NULL OR v_user_credits < 1 THEN
        RAISE EXCEPTION 'Not enough credits (have: %, need: 1)', COALESCE(v_user_credits, 0);
    END IF;

    -- 5. Decrement credits
    v_new_credits := v_user_credits - 1;
    UPDATE public.users SET credits = v_new_credits, updated_at = NOW() WHERE id = v_user_id;

    -- 6. Create job with tg_user_id for fast worker access
    INSERT INTO public.jobs (
        user_id,
        tg_user_id,
        idempotency_key,
        kind,
        input_photo_path,
        product_info,
        extra_wishes,
        template_id,
        status
    )
    VALUES (
        v_user_id,
        p_tg_user_id,
        p_idempotency_key,
        p_kind,
        p_input_photo_path,
        p_product_info,
        p_extra_wishes,
        p_template_id,
        'queued'
    )
    RETURNING id INTO v_job_id;

    -- 7. Return results
    RETURN QUERY SELECT v_job_id, v_new_credits;
END;
$$;

-- 6. Add comment for documentation
COMMENT ON COLUMN public.jobs.tg_user_id IS 'Denormalized Telegram user ID for fast worker access without JOIN';
