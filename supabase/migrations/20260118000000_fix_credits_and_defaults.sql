-- Migration: Add default credits and fix balance field
-- Run this to update existing database

-- 1. Ensure all users have at least credits field (not balance)
DO $$
BEGIN
    -- Check if 'balance' column exists and migrate to 'credits'
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'users' AND column_name = 'balance'
    ) THEN
        -- Copy balance to credits if credits doesn't exist
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'users' AND column_name = 'credits'
        ) THEN
            ALTER TABLE public.users ADD COLUMN credits INT;
            UPDATE public.users SET credits = COALESCE(balance, 2);
        END IF;
        
        -- Drop balance column
        ALTER TABLE public.users DROP COLUMN IF EXISTS balance;
    END IF;
END $$;

-- 2. Set default value for credits
ALTER TABLE public.users 
ALTER COLUMN credits SET DEFAULT 2,
ALTER COLUMN credits SET NOT NULL;

-- 3. Give existing users without credits 2 free credits
UPDATE public.users 
SET credits = 2 
WHERE credits IS NULL OR credits = 0;

-- 4. Update RPC function with better error messages
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
    -- 1. Check for existing job
    SELECT id INTO v_existing_job_id FROM public.jobs WHERE idempotency_key = p_idempotency_key;
    IF v_existing_job_id IS NOT NULL THEN
        SELECT credits INTO v_new_credits FROM public.users WHERE tg_user_id = p_tg_user_id;
        RETURN QUERY SELECT v_existing_job_id, COALESCE(v_new_credits, 0);
        RETURN;
    END IF;

    -- 2. Get user and lock
    SELECT id, credits INTO v_user_id, v_user_credits 
    FROM public.users 
    WHERE tg_user_id = p_tg_user_id 
    FOR UPDATE;

    -- 3. Validate
    IF v_user_id IS NULL THEN
        RAISE EXCEPTION 'User with tg_user_id % not found', p_tg_user_id;
    END IF;

    IF v_user_credits IS NULL OR v_user_credits < 1 THEN
        RAISE EXCEPTION 'Not enough credits (have: %, need: 1)', COALESCE(v_user_credits, 0);
    END IF;

    -- 4. Consume credit
    v_new_credits := v_user_credits - 1;
    UPDATE public.users SET credits = v_new_credits WHERE id = v_user_id;

    -- 5. Create job
    INSERT INTO public.jobs (
        user_id,
        idempotency_key,
        kind,
        input_photo_path,
        product_info,
        extra_wishes,
        template_id,
        status
    ) VALUES (
        v_user_id,
        p_idempotency_key,
        p_kind,
        p_input_photo_path,
        p_product_info,
        p_extra_wishes,
        p_template_id,
        'queued'
    ) RETURNING id INTO v_job_id;

    RETURN QUERY SELECT v_job_id, v_new_credits;
END;
$$;
