-- ===================================
-- NEUROCARDS BOT DATABASE SCHEMA
-- ===================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ===================================
-- USERS TABLE
-- ===================================
CREATE TABLE IF NOT EXISTS public.users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tg_user_id BIGINT UNIQUE NOT NULL,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    credits INT DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_users_tg_user_id ON public.users(tg_user_id);
CREATE INDEX idx_users_created_at ON public.users(created_at DESC);

-- ===================================
-- JOBS TABLE (Video Generation Tasks)
-- ===================================
CREATE TABLE IF NOT EXISTS public.jobs (
    id TEXT PRIMARY KEY,
    tg_user_id BIGINT NOT NULL REFERENCES public.users(tg_user_id) ON DELETE CASCADE,
    user_id UUID REFERENCES public.users(id) ON DELETE CASCADE,
    
    -- Task details
    product_name TEXT NOT NULL,
    product_image_url TEXT,
    product_text TEXT,
    extra_wishes TEXT,

    -- Idempotency key to avoid duplicate jobs
    idempotency_key TEXT UNIQUE,
    
    -- Generation details
    prompt TEXT,
    kie_task_id TEXT,
    kie_api_key TEXT,
    
    -- Status and progress
    status TEXT DEFAULT 'queued' CHECK (status IN ('queued', 'processing', 'completed', 'failed')),
    progress INT DEFAULT 0,
    
    -- Results
    video_url TEXT,
    video_file_id TEXT,
    
    -- Error handling
    error TEXT,
    error_details JSONB,
    attempts INT DEFAULT 0,
    
    -- Financial
    credits_deducted INT DEFAULT 1,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    started_at TIMESTAMP WITH TIME ZONE,
    finished_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_jobs_tg_user_id ON public.jobs(tg_user_id);
CREATE INDEX idx_jobs_status ON public.jobs(status);
CREATE INDEX idx_jobs_created_at ON public.jobs(created_at DESC);
CREATE INDEX idx_jobs_idempotency_key ON public.jobs(idempotency_key);
CREATE INDEX idx_jobs_kie_task_id ON public.jobs(kie_task_id);

-- ===================================
-- FUNCTION: create_job_and_consume_credit
-- ===================================
CREATE OR REPLACE FUNCTION public.create_job_and_consume_credit(
    p_tg_user_id BIGINT,
    p_template_type TEXT,
    p_idempotency_key TEXT,
    p_photo_path TEXT,
    p_prompt_input TEXT
) RETURNS JSON AS $$
DECLARE
    v_user_id UUID;
    v_credits INT;
    v_job_id TEXT;
BEGIN
    -- 1) Найти пользователя и заблокировать строку
    SELECT id, credits INTO v_user_id, v_credits
    FROM public.users
    WHERE tg_user_id = p_tg_user_id
    FOR UPDATE;

    IF v_user_id IS NULL THEN
        RAISE EXCEPTION 'User % not found', p_tg_user_id;
    END IF;

    -- 2) Проверить существующий job по идемпотентности
    SELECT id INTO v_job_id
    FROM public.jobs
    WHERE idempotency_key = p_idempotency_key;

    IF v_job_id IS NOT NULL THEN
        RETURN json_build_object('job_id', v_job_id, 'new_credits', v_credits);
    END IF;

    -- 3) Проверить баланс
    IF v_credits <= 0 THEN
        RAISE EXCEPTION 'Not enough credits';
    END IF;

    -- 4) Списать 1 кредит
    UPDATE public.users
    SET credits = credits - 1, updated_at = NOW()
    WHERE id = v_user_id;

    -- 5) Создать job
    v_job_id := gen_random_uuid()::text;
    INSERT INTO public.jobs (
        id,
        tg_user_id,
        user_id,
        product_name,
        product_image_url,
        product_text,
        extra_wishes,
        prompt,
        status,
        credits_deducted,
        idempotency_key
    ) VALUES (
        v_job_id,
        p_tg_user_id,
        v_user_id,
        p_template_type,
        p_photo_path,
        p_prompt_input,
        NULL,
        p_prompt_input,
        'queued',
        1,
        p_idempotency_key
    );

    -- 6) Вернуть результат
    RETURN json_build_object(
        'job_id', v_job_id,
        'new_credits', v_credits - 1
    );
END;
$$ LANGUAGE plpgsql;

-- ===================================
-- CREDITS HISTORY TABLE
-- ===================================
CREATE TABLE IF NOT EXISTS public.credits_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tg_user_id BIGINT NOT NULL REFERENCES public.users(tg_user_id) ON DELETE CASCADE,
    user_id UUID REFERENCES public.users(id) ON DELETE CASCADE,
    
    -- Transaction details
    amount INT NOT NULL,
    operation_type TEXT NOT NULL CHECK (operation_type IN ('purchase', 'usage', 'refund', 'bonus', 'expired')),
    job_id TEXT REFERENCES public.jobs(id) ON DELETE SET NULL,
    
    -- Metadata
    description TEXT,
    metadata JSONB,
    
    -- Timestamp
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_credits_history_tg_user_id ON public.credits_history(tg_user_id);
CREATE INDEX idx_credits_history_operation ON public.credits_history(operation_type);
CREATE INDEX idx_credits_history_created_at ON public.credits_history(created_at DESC);

-- ===================================
-- PRICING PLANS TABLE
-- ===================================
CREATE TABLE IF NOT EXISTS public.pricing_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    name_ru TEXT NOT NULL,
    credits_amount INT NOT NULL,
    price_rub DECIMAL(10,2) NOT NULL,
    price_usd DECIMAL(10,2),
    bonus_credits INT DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ===================================
-- PAYMENTS TABLE
-- ===================================
CREATE TABLE IF NOT EXISTS public.payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    tg_user_id BIGINT NOT NULL,
    plan_id UUID REFERENCES public.pricing_plans(id),
    
    -- Financial data
    amount_rub DECIMAL(10,2),
    amount_usd DECIMAL(10,2),
    currency TEXT DEFAULT 'RUB' CHECK (currency IN ('RUB', 'USD')),
    credits_purchased INT NOT NULL,
    
    -- Payment status
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'completed', 'failed', 'refunded')),
    
    -- Payment provider
    payment_provider TEXT,
    payment_id TEXT,
    payment_url TEXT,
    
    -- Metadata
    metadata JSONB,
    error_message TEXT,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    refunded_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_payments_tg_user_id ON public.payments(tg_user_id);
CREATE INDEX idx_payments_status ON public.payments(status);
CREATE INDEX idx_payments_created_at ON public.payments(created_at DESC);

-- ===================================
-- INSERT DEFAULT PRICING PLANS
-- ===================================
INSERT INTO public.pricing_plans (name, name_ru, credits_amount, price_rub, bonus_credits, is_active)
VALUES 
    ('starter', 'Стартер', 5, 199.00, 0, TRUE),
    ('pro', 'Профи', 20, 699.00, 2, TRUE),
    ('premium', 'Премиум', 50, 1499.00, 10, TRUE)
ON CONFLICT (name) DO NOTHING;

-- ===================================
-- FUNCTION: refund_credit
-- ===================================
CREATE OR REPLACE FUNCTION public.refund_credit(p_tg_user_id BIGINT)
RETURNS INT AS $$
DECLARE
    v_new_credits INT;
BEGIN
    UPDATE public.users
    SET credits = credits + 1, updated_at = NOW()
    WHERE tg_user_id = p_tg_user_id
    RETURNING credits INTO v_new_credits;
    
    -- Логируем в историю
    INSERT INTO public.credits_history (tg_user_id, amount, operation_type, description)
    SELECT p_tg_user_id, 1, 'refund', 'Job failed - credit refunded'
    WHERE EXISTS (SELECT 1 FROM public.users WHERE tg_user_id = p_tg_user_id);
    
    RETURN COALESCE(v_new_credits, 0);
END;
$$ LANGUAGE plpgsql;

-- ===================================
-- FUNCTION: add_credits
-- ===================================
CREATE OR REPLACE FUNCTION public.add_credits(p_tg_user_id BIGINT, p_amount INT, p_operation_type TEXT DEFAULT 'bonus')
RETURNS INT AS $$
DECLARE
    v_new_credits INT;
BEGIN
    IF p_amount <= 0 THEN
        RAISE EXCEPTION 'Amount must be positive';
    END IF;
    
    UPDATE public.users
    SET credits = credits + p_amount, updated_at = NOW()
    WHERE tg_user_id = p_tg_user_id
    RETURNING credits INTO v_new_credits;
    
    -- Логируем в историю
    INSERT INTO public.credits_history (tg_user_id, amount, operation_type, description)
    SELECT p_tg_user_id, p_amount, p_operation_type, 'Credits added: ' || p_operation_type
    WHERE EXISTS (SELECT 1 FROM public.users WHERE tg_user_id = p_tg_user_id);
    
    RETURN COALESCE(v_new_credits, 0);
END;
$$ LANGUAGE plpgsql;

-- ===================================
-- FUNCTION: complete_payment
-- ===================================
CREATE OR REPLACE FUNCTION public.complete_payment(
    p_payment_id UUID,
    p_tg_user_id BIGINT,
    p_credits_amount INT
)
RETURNS JSON AS $$
DECLARE
    v_user_id UUID;
    v_new_credits INT;
    v_payment RECORD;
BEGIN
    -- 1) Получить информацию о платеже
    SELECT * INTO v_payment FROM public.payments WHERE id = p_payment_id FOR UPDATE;
    
    IF v_payment IS NULL THEN
        RETURN json_build_object('success', FALSE, 'error', 'Payment not found');
    END IF;
    
    IF v_payment.status != 'pending' THEN
        RETURN json_build_object('success', FALSE, 'error', 'Payment already processed');
    END IF;
    
    -- 2) Получить пользователя
    SELECT id INTO v_user_id FROM public.users WHERE tg_user_id = p_tg_user_id;
    IF v_user_id IS NULL THEN
        RETURN json_build_object('success', FALSE, 'error', 'User not found');
    END IF;
    
    -- 3) Обновить платеж
    UPDATE public.payments
    SET status = 'completed', completed_at = NOW()
    WHERE id = p_payment_id;
    
    -- 4) Добавить кредиты
    UPDATE public.users
    SET credits = credits + p_credits_amount, updated_at = NOW()
    WHERE tg_user_id = p_tg_user_id
    RETURNING credits INTO v_new_credits;
    
    -- 5) Логировать в историю
    INSERT INTO public.credits_history (tg_user_id, amount, operation_type, description)
    VALUES (p_tg_user_id, p_credits_amount, 'purchase', 'Payment completed: ' || p_payment_id);
    
    RETURN json_build_object(
        'success', TRUE,
        'new_credits', v_new_credits,
        'payment_id', p_payment_id
    );
END;
$$ LANGUAGE plpgsql;

-- ===================================
-- RLS (Row Level Security) - DISABLED FOR NOW
-- ===================================
-- Can be enabled for multi-tenant security if needed
