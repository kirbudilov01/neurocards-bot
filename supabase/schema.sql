-- Complete schema for neurocards-bot database
-- Run this in your Supabase SQL editor or local PostgreSQL

-- ===================================
-- USERS TABLE
-- ===================================
CREATE TABLE IF NOT EXISTS public.users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tg_user_id BIGINT UNIQUE NOT NULL,
    username TEXT,
    credits INT DEFAULT 2 NOT NULL,  -- 2 бесплатных токена по умолчанию
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index for fast lookup by Telegram user ID
CREATE INDEX IF NOT EXISTS idx_users_tg_user_id ON public.users(tg_user_id);

-- ===================================
-- JOBS TABLE
-- ===================================
CREATE TABLE IF NOT EXISTS public.jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    idempotency_key TEXT UNIQUE,
    kind TEXT DEFAULT 'reels',
    template_id TEXT DEFAULT 'ugc',
    input_photo_path TEXT NOT NULL,
    product_info JSONB,
    extra_wishes TEXT,
    status TEXT DEFAULT 'queued' CHECK (status IN ('queued', 'processing', 'done', 'failed')),
    kie_task_id TEXT,
    output_url TEXT,
    error TEXT,
    attempts INT DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    started_at TIMESTAMP WITH TIME ZONE,
    finished_at TIMESTAMP WITH TIME ZONE
);

-- Indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_jobs_user_id ON public.jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON public.jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON public.jobs(created_at);
CREATE INDEX IF NOT EXISTS idx_jobs_idempotency_key ON public.jobs(idempotency_key);

-- Composite index for worker queries
CREATE INDEX IF NOT EXISTS idx_jobs_status_created_at ON public.jobs(status, created_at);

-- ===================================
-- RPC FUNCTIONS
-- ===================================

-- Function: Create job and consume credit atomically
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

    -- 6. Create job
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

    -- 7. Return results
    RETURN QUERY SELECT v_job_id, v_new_credits;
END;
$$;

-- Function: Refund credit to user
CREATE OR REPLACE FUNCTION refund_credit(
    p_tg_user_id BIGINT,
    p_amount INT DEFAULT 1
)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    UPDATE public.users 
    SET credits = credits + p_amount,
        updated_at = NOW()
    WHERE tg_user_id = p_tg_user_id;
    
    IF NOT FOUND THEN
        RAISE EXCEPTION 'User with tg_user_id % not found', p_tg_user_id;
    END IF;
END;
$$;

-- ===================================
-- TRIGGERS
-- ===================================

-- Auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON public.users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ===================================
-- PERMISSIONS (if using RLS)
-- ===================================

-- Enable RLS
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.jobs ENABLE ROW LEVEL SECURITY;

-- Service role has full access
CREATE POLICY "Service role has full access to users" ON public.users
    FOR ALL
    USING (true)
    WITH CHECK (true);

CREATE POLICY "Service role has full access to jobs" ON public.jobs
    FOR ALL
    USING (true)
    WITH CHECK (true);

