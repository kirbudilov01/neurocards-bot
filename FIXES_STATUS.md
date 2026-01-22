# 🔧 ИСПРАВЛЕНИЯ И ТЕКУЩИЙ СТАТУС

**Дата:** 2026-01-22 19:44 UTC  
**Обновление:** Критичные баги исправлены

---

## ✅ **ЧТО ИСПРАВЛЕНО:**

### 1. **refund_credit() signature** ✅
**Проблема:** Worker вызывал `refund_credit(tg_user_id, 1)` но функция принимает только 1 аргумент  
**Решение:** Заменил все вызовы на `refund_credit(tg_user_id)` (amount=1 по умолчанию)  
**Файлы:** `worker/worker.py` (3 места)

### 2. **Выбор количества видео (1/3/5)** ✅
**Проблема:** После ввода пожеланий флоу сразу шёл на confirm, минуя выбор количества  
**Решение:** Добавил state `waiting_video_count` с кнопками 1/3/5 видео  
**Файлы:** `app/handlers/menu_and_flow.py`

**Теперь флоу:**
```
Фото → Товар → Шаблон → Пожелания → [КОЛИЧЕСТВО 1/3/5] → Подтверждение → Генерация
```

### 3. **get_public_input_url() для внешних URL** ✅
**Проблема:** Функция возвращала None для https:// URLs  
**Решение:** Добавил проверку `if url.startswith(("http://", "https://"))` return url  
**Файлы:** `worker/worker.py`

### 4. **KIE API aspect_ratio** ✅
**Проблема:** KIE возвращал ошибку 500 "aspect_ratio is not within the range of allowed options"  
**Решение:** Убрал `aspect_ratio` из payload - KIE определяет автоматически по размеру изображения  
**Файлы:** `worker/kie_client.py`

### 5. **Worker cache issues** ✅
**Проблема:** Python кэшировал .pyc файлы, код не обновлялся  
**Решение:** Добавил очистку `__pycache__` перед restart  
**Команда:**
```bash
find . -name '__pycache__' -type d -exec rm -rf {} +
find . -name '*.pyc' -delete
systemctl restart 'neurocards-worker@*'
```

---

## ⚠️ **ОСТАЛОСЬ ДОДЕЛАТЬ:**

### 1. Кнопки после генерации
**Нужно:** "Сделать ещё с этим товаром" + "Вернуться в меню"  
**Где:** После успешной отправки видео пользователю  
**Файлы:** `worker/worker.py` (строка ~340)

**Реализация:**
```python
# После отправки видео
reply_markup = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🔄 Сделать ещё с этим товаром", callback_data="retry_same_product")],
    [InlineKeyboardButton(text="🏠 Вернуться в меню", callback_data="back_to_menu")]
])

await bot.send_video(
    tg_user_id,
    video=BufferedInputFile(data, filename="result.mp4"),
    caption="✅ Видео готово!",
    reply_markup=reply_markup,
)
```

**Handler для "retry_same_product":**
```python
@router.callback_query(F.data == "retry_same_product")
async def retry_generation(cb: CallbackQuery, state: FSMContext):
    # Загрузить данные предыдущей генерации из БД или state
    # Вернуть к выбору шаблона (минуя фото и товар)
    await cb.answer()
    await cb.message.answer(
        "Выбери формат видео:",
        reply_markup=kb_template_type(),
    )
    await state.set_state(GenFlow.waiting_template_type)
```

### 2. Проблема с дублями сообщений
**Причина:** Возможно несколько одновременных запросов от Telegram (webhook + polling?)  
**Проверить:** Что бот работает ТОЛЬКО через webhook ИЛИ polling, не оба  
**Файл:** `app/bot_webhook.py` + `app/bot_polling.py`

### 3. HTTPS Webhook
**Текущий статус:** HTTP на :10000  
**Нужен:** HTTPS для Telegram webhook  
**Быстрое решение:** ngrok

```bash
ngrok http 10000
# Получить URL: https://xxx.ngrok-free.app
# Обновить .env: PUBLIC_BASE_URL=https://xxx.ngrok-free.app
systemctl restart neurocards-bot
```

---

## 🧪 **ТЕСТИРОВАНИЕ:**

### Как протестировать сейчас:

1. **Через SQL (обходя Telegram):**
```sql
INSERT INTO jobs (
  user_id, tg_user_id, idempotency_key, 
  kind, template_id, input_photo_path, 
  product_info, status
) VALUES (
  (SELECT id FROM users WHERE tg_user_id = 5235703016),
  5235703016,
  'manual_test_' || extract(epoch from now())::text,
  'reels',
  'self',
  'https://picsum.photos/1080/1920',  -- Публичное изображение
  '{"text": "Test", "user_prompt": "A cinematic product showcase"}',
  'queued'
);
```

Worker подхватит автоматически!

2. **Через Telegram (нужен HTTPS webhook):**
- /start
- Сделать Reels
- Отправить фото
- Пройти флоу
- Теперь должен спросить: "Сколько видео сделать? 1/3/5"

---

## 📊 **СТАТУС БАГОВ:**

| Баг | Статус | Приоритет |
|-----|--------|-----------|
| refund_credit() signature | ✅ Исправлен | Critical |
| Выбор количества видео (1/3/5) | ✅ Исправлен | Critical |
| KIE aspect_ratio | ✅ Исправлен | Critical |
| get_public_input_url() | ✅ Исправлен | High |
| Worker cache | ✅ Исправлен | High |
| Кнопки после генерации | ⚠️ Todo | Medium |
| Дубли сообщений | ⚠️ Investigate | Medium |
| HTTPS webhook | ⚠️ Todo | Medium |

---

## 🎯 **СЛЕДУЮЩИЕ ШАГИ:**

1. **Настроить HTTPS webhook** (15 минут)
2. **Добавить кнопки после генерации** (10 минут)
3. **Протестировать end-to-end** через Telegram
4. **Исправить дубли** если ещё проявляются

---

## 📝 **КОМАНДЫ ДЛЯ МОНИТОРИНГА:**

```bash
# Логи worker'ов
tail -f /var/log/syslog | grep neurocards-worker

# Статус
systemctl status 'neurocards-worker@*' | grep Active | wc -l

# Последние job'ы
sudo -u postgres psql -d neurocards -c "
  SELECT id::text, status, error, created_at 
  FROM jobs 
  WHERE tg_user_id=5235703016 
  ORDER BY created_at DESC 
  LIMIT 5;
"

# Баланс
sudo -u postgres psql -d neurocards -c "
  SELECT credits 
  FROM users 
  WHERE tg_user_id=5235703016;
"
```

---

**Итог:** Основные баги исправлены! Система работает, осталось только UI доработки (кнопки) и HTTPS webhook.
