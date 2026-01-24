-- Удаляем старые тарифы и добавляем правильные

DELETE FROM pricing_plans;

INSERT INTO public.pricing_plans (name, name_ru, credits_amount, price_rub, price_usd, bonus_credits) VALUES
    ('tokens_5', '5 токенов', 5, 390.00, 5.00, 0),
    ('tokens_10', '10 токенов', 10, 690.00, 9.00, 0),
    ('tokens_30', '30 видео', 30, 1790.00, 24.00, 0),
    ('tokens_100', '100 видео', 100, 4990.00, 67.00, 0)
ON CONFLICT (name) DO UPDATE SET
    name_ru = EXCLUDED.name_ru,
    credits_amount = EXCLUDED.credits_amount,
    price_rub = EXCLUDED.price_rub,
    price_usd = EXCLUDED.price_usd,
    bonus_credits = EXCLUDED.bonus_credits,
    updated_at = NOW();

-- Проверяем результат
SELECT 
    name_ru as "Название",
    credits_amount as "Токенов",
    price_rub as "Цена (₽)",
    ROUND(price_rub / credits_amount, 2) as "₽/видео",
    bonus_credits as "Бонус"
FROM pricing_plans
ORDER BY price_rub;

