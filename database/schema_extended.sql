-- ===================================
-- ДОПОЛНЕНИЕ К СХЕМЕ: ПЛАТЕЖИ И ТАРИФЫ
-- ===================================

-- Таблица тарифных планов
CREATE TABLE IF NOT EXISTS public.pricing_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,  -- 'starter', 'pro', 'premium'
    name_ru TEXT NOT NULL,      -- 'Стартер', 'Профи', 'Премиум'
    credits_amount INT NOT NULL, -- Количество токенов
    price_rub DECIMAL(10,2) NOT NULL, -- Цена в рублях
    price_usd DECIMAL(10,2),     -- Цена в долларах
    bonus_credits INT DEFAULT 0, -- Бонусные токены
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Таблица платежей
CREATE TABLE IF NOT EXISTS public.payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    tg_user_id BIGINT NOT NULL, -- Денормализация
    plan_id UUID REFERENCES public.pricing_plans(id),
    
    -- Финансовые данные
    amount_rub DECIMAL(10,2),   -- Сумма в рублях
    amount_usd DECIMAL(10,2),   -- Сумма в долларах
    currency TEXT DEFAULT 'RUB', -- 'RUB', 'USD'
    credits_purchased INT NOT NULL, -- Куплено токенов
    
    -- Статус платежа
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'completed', 'failed', 'refunded')),
    
    -- Интеграция с платежной системой
    payment_provider TEXT,      -- 'yookassa', 'stripe', 'crypto', etc.
    payment_id TEXT,            -- ID платежа в системе провайдера
    payment_url TEXT,           -- URL для оплаты
    
    -- Метаданные
    metadata JSONB,             -- Дополнительные данные
    error_message TEXT,         -- Ошибка при неудачном платеже
    
    -- Временные метки
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    refunded_at TIMESTAMP WITH TIME ZONE
);

-- Индексы для payments
CREATE INDEX IF NOT EXISTS idx_payments_user_id ON public.payments(user_id);
CREATE INDEX IF NOT EXISTS idx_payments_tg_user_id ON public.payments(tg_user_id);
CREATE INDEX IF NOT EXISTS idx_payments_status ON public.payments(status);
CREATE INDEX IF NOT EXISTS idx_payments_created_at ON public.payments(created_at);
CREATE INDEX IF NOT EXISTS idx_payments_payment_id ON public.payments(payment_id);

-- Композитный индекс для аналитики
CREATE INDEX IF NOT EXISTS idx_payments_status_created ON public.payments(status, created_at);

-- ===================================
-- НАЧАЛЬНЫЕ ДАННЫЕ: ТАРИФНЫЕ ПЛАНЫ
-- ===================================

INSERT INTO public.pricing_plans (name, name_ru, credits_amount, price_rub, price_usd, bonus_credits) VALUES
    ('starter_10', 'Стартер (10)', 10, 500.00, 5.00, 0),
    ('basic_25', 'Базовый (25)', 25, 1200.00, 12.00, 3),
    ('pro_50', 'Профи (50)', 50, 2300.00, 23.00, 7),
    ('premium_100', 'Премиум (100)', 100, 4200.00, 42.00, 20),
    ('enterprise_250', 'Корпоративный (250)', 250, 9900.00, 99.00, 75)
ON CONFLICT (name) DO NOTHING;

-- ===================================
-- RPC ФУНКЦИИ ДЛЯ ПЛАТЕЖЕЙ
-- ===================================

-- Функция для создания платежа
CREATE OR REPLACE FUNCTION create_payment(
    p_tg_user_id BIGINT,
    p_plan_id UUID,
    p_amount_rub DECIMAL,
    p_amount_usd DECIMAL,
    p_currency TEXT,
    p_provider TEXT
) RETURNS UUID AS $$
DECLARE
    v_user_id UUID;
    v_payment_id UUID;
    v_credits INT;
BEGIN
    -- Получить user_id
    SELECT id INTO v_user_id FROM users WHERE tg_user_id = p_tg_user_id;
    
    -- Получить количество токенов из плана
    SELECT credits_amount + bonus_credits INTO v_credits 
    FROM pricing_plans 
    WHERE id = p_plan_id;
    
    -- Создать платеж
    INSERT INTO payments (
        user_id,
        tg_user_id,
        plan_id,
        amount_rub,
        amount_usd,
        currency,
        credits_purchased,
        payment_provider,
        status
    ) VALUES (
        v_user_id,
        p_tg_user_id,
        p_plan_id,
        p_amount_rub,
        p_amount_usd,
        p_currency,
        v_credits,
        p_provider,
        'pending'
    )
    RETURNING id INTO v_payment_id;
    
    RETURN v_payment_id;
END;
$$ LANGUAGE plpgsql;

-- Функция для подтверждения платежа (начисление токенов)
CREATE OR REPLACE FUNCTION complete_payment(
    p_payment_id UUID,
    p_external_payment_id TEXT
) RETURNS VOID AS $$
DECLARE
    v_user_id UUID;
    v_credits INT;
    v_tg_user_id BIGINT;
BEGIN
    -- Получить данные платежа
    SELECT user_id, credits_purchased, tg_user_id INTO v_user_id, v_credits, v_tg_user_id
    FROM payments
    WHERE id = p_payment_id AND status = 'pending';
    
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Payment not found or already processed';
    END IF;
    
    -- Начислить токены
    UPDATE users
    SET credits = credits + v_credits,
        updated_at = NOW()
    WHERE id = v_user_id;
    
    -- Обновить статус платежа
    UPDATE payments
    SET status = 'completed',
        payment_id = p_external_payment_id,
        completed_at = NOW()
    WHERE id = p_payment_id;
    
END;
$$ LANGUAGE plpgsql;

-- Функция для возврата платежа
CREATE OR REPLACE FUNCTION refund_payment(
    p_payment_id UUID,
    p_error_message TEXT DEFAULT NULL
) RETURNS VOID AS $$
DECLARE
    v_user_id UUID;
    v_credits INT;
BEGIN
    -- Получить данные платежа
    SELECT user_id, credits_purchased INTO v_user_id, v_credits
    FROM payments
    WHERE id = p_payment_id AND status = 'completed';
    
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Payment not found or not completed';
    END IF;
    
    -- Вернуть токены (если они не были использованы)
    UPDATE users
    SET credits = GREATEST(credits - v_credits, 0),
        updated_at = NOW()
    WHERE id = v_user_id;
    
    -- Обновить статус платежа
    UPDATE payments
    SET status = 'refunded',
        error_message = p_error_message,
        refunded_at = NOW()
    WHERE id = p_payment_id;
    
END;
$$ LANGUAGE plpgsql;

-- ===================================
-- ТРИГГЕРЫ
-- ===================================

CREATE TRIGGER update_pricing_plans_updated_at
    BEFORE UPDATE ON pricing_plans
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

