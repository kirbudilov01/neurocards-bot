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
CREATE INDEX idx_jobs_kie_task_id ON public.jobs(kie_task_id);

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
-- RLS (Row Level Security) - DISABLED FOR NOW
-- ===================================
-- Can be enabled for multi-tenant security if needed
