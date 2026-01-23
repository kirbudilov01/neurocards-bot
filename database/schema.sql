-- Complete schema for neurocards-bot database
-- PostgreSQL schema for VPS deployment
-- Run this on your local PostgreSQL instance

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
    tg_user_id BIGINT,  -- Денормализация для быстрого поиска
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
CREATE INDEX IF NOT EXISTS idx_jobs_tg_user_id ON public.jobs(tg_user_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON public.jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON public.jobs(created_at);
CREATE INDEX IF NOT EXISTS idx_jobs_idempotency_key ON public.jobs(idempotency_key);

-- Composite index for worker queries
CREATE INDEX IF NOT EXISTS idx_jobs_status_created_at ON public.jobs(status, created_at);

-- ===================================
-- RPC FUNCTIONS
-- ===================================

-- Function to create job and consume credit atomically
CREATE OR REPLACE FUNCTION create_job_and_consume_credit(
    p_tg_user_id BIGINT,
    p_template_type TEXT,
    p_idempotency_key TEXT,
    p_photo_path TEXT,
    p_prompt_input JSONB
) RETURNS JSON AS $$
DECLARE
    v_user_id UUID;
    v_new_credits INT;
    v_job_id UUID;
    v_result JSON;
BEGIN
    -- Get or create user
    INSERT INTO users (tg_user_id)
    VALUES (p_tg_user_id)
    ON CONFLICT (tg_user_id) DO UPDATE SET updated_at = NOW()
    RETURNING id, credits INTO v_user_id, v_new_credits;

    -- Check if user has enough credits
    IF v_new_credits < 1 THEN
        RAISE EXCEPTION 'Not enough credits';
    END IF;

    -- Deduct credit
    UPDATE users
    SET credits = credits - 1,
        updated_at = NOW()
    WHERE id = v_user_id
    RETURNING credits INTO v_new_credits;

    -- Create job
    INSERT INTO jobs (
        user_id,
        tg_user_id,
        kind,
        template_id,
        idempotency_key,
        input_photo_path,
        product_info,
        status
    ) VALUES (
        v_user_id,
        p_tg_user_id,
        p_template_type,
        'ugc',
        p_idempotency_key,
        p_photo_path,
        p_prompt_input,
        'queued'
    )
    RETURNING id INTO v_job_id;

    -- Return result
    v_result := json_build_object(
        'job_id', v_job_id,
        'new_credits', v_new_credits
    );

    RETURN v_result;
END;
$$ LANGUAGE plpgsql;

-- Function to refund credit when job fails
CREATE OR REPLACE FUNCTION refund_credit(p_tg_user_id BIGINT)
RETURNS VOID AS $$
BEGIN
    UPDATE users
    SET credits = credits + 1,
        updated_at = NOW()
    WHERE tg_user_id = p_tg_user_id;
END;
$$ LANGUAGE plpgsql;

-- Function to get user balance
CREATE OR REPLACE FUNCTION get_user_balance(p_tg_user_id BIGINT)
RETURNS INT AS $$
DECLARE
    v_credits INT;
BEGIN
    SELECT credits INTO v_credits
    FROM users
    WHERE tg_user_id = p_tg_user_id;
    
    RETURN COALESCE(v_credits, 2);  -- Default 2 credits for new users
END;
$$ LANGUAGE plpgsql;

-- ===================================
-- TRIGGERS
-- ===================================

-- Trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ===================================
-- INDEXES FOR PERFORMANCE
-- ===================================

-- Additional indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_jobs_kie_task_id ON public.jobs(kie_task_id) WHERE kie_task_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_jobs_status_started ON public.jobs(status, started_at) WHERE status = 'processing';

-- ===================================
-- PERMISSIONS (Optional, for security)
-- ===================================

-- Grant permissions to bot user (if using dedicated user)
-- GRANT SELECT, INSERT, UPDATE ON users TO botuser;
-- GRANT SELECT, INSERT, UPDATE ON jobs TO botuser;
-- GRANT EXECUTE ON FUNCTION create_job_and_consume_credit TO botuser;
-- GRANT EXECUTE ON FUNCTION refund_credit TO botuser;
-- GRANT EXECUTE ON FUNCTION get_user_balance TO botuser;
