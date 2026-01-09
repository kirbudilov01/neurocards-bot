-- Add a unique idempotency key to the jobs table to prevent duplicate jobs.
ALTER TABLE public.jobs
ADD COLUMN idempotency_key TEXT UNIQUE;

-- Create an index on the new column for faster lookups.
CREATE INDEX idx_jobs_idempotency_key ON public.jobs(idempotency_key);

-- Create the RPC function to create a job and consume a credit in a single transaction.
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
    -- 1. Check for an existing job with the same idempotency key.
    SELECT id INTO v_existing_job_id FROM public.jobs WHERE idempotency_key = p_idempotency_key;
    IF v_existing_job_id IS NOT NULL THEN
        -- If the job already exists, return its ID and the user's current credit balance.
        SELECT credits INTO v_new_credits FROM public.users WHERE tg_user_id = p_tg_user_id;
        RETURN QUERY SELECT v_existing_job_id, v_new_credits;
        RETURN;
    END IF;

    -- 2. Get the user's UUID and current credit balance, locking the row for the transaction.
    SELECT id, credits INTO v_user_id, v_user_credits FROM public.users WHERE tg_user_id = p_tg_user_id FOR UPDATE;

    -- 3. If user doesn't exist or has insufficient credits, raise an exception.
    IF v_user_id IS NULL THEN
        RAISE EXCEPTION 'User with tg_user_id % not found', p_tg_user_id;
    END IF;

    IF v_user_credits IS NULL OR v_user_credits < 1 THEN
        RAISE EXCEPTION 'Not enough credits';
    END IF;

    -- 4. Decrement the user's credits.
    v_new_credits := v_user_credits - 1;
    UPDATE public.users SET credits = v_new_credits WHERE id = v_user_id;

    -- 5. Insert the new job with the status 'queued'.
    INSERT INTO public.jobs (
        user_id,
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
        p_idempotency_key,
        p_kind,
        p_input_photo_path,
        p_product_info,
        p_extra_wishes,
        p_template_id,
        'queued'
    )
    RETURNING id INTO v_job_id;

    -- 6. Return the new job's ID and the user's new credit balance.
    RETURN QUERY SELECT v_job_id, v_new_credits;
END;
$$;
