# 📋 ERROR HANDLING STRATEGY

## 🎯 ОСНОВНОЙ ПРИНЦИП

**Retry должен работать ТОХо же от ошибок!** ✅ (Уже работает)

Вопрос: когда уведомлять пользователя?

---

## 🔍 ТИПЫ ОШИБОК И СТРАТЕГИЯ

### 1️⃣ TRANSIENT ERRORS (временные)
**Примеры**:
- KIE.AI timeout (генерация долго)
- sendVideo timeout (Telegram занят)
- 429 Too Many Requests (rate limit)
- 503 Service Unavailable (API перегруженна)

**Что делать**:
- ✅ Retry автоматически (уже работает)
- ✅ **НЕ уведомлять пользователя** (не нужно, они не могут помочь)
- ✅ Если будет очень долго (>10 min) - тогда пишем "подождите"

**Обработка**: просто `continue` в retry loop

---

### 2️⃣ USER ERRORS (юзер что-то неправильно сделал)
**Примеры**:
- Photo is too dark / blurry
- No product detected in image
- Image too small
- Bad file format
- Adult content detected

**Что делать**:
- ❌ НЕ retry (не поможет)
- ✅ **Уведомить пользователя**: "Фото слишком темное, попробуй с лучшим освещением"
- ✅ Вернуть кредиты
- ✅ Предложить попробовать еще раз с новым фото

**Обработка**: `classify_kie_error()` → `'user_error'` → refund + message

---

### 3️⃣ SYSTEM ERRORS (что-то сломалось в системе)
**Примеры**:
- Database connection lost
- Redis connection lost
- Worker crash
- Invalid API response
- Corrupted video file

**Что делать**:
- ⚠️ **Можно retry** (может быть временно)
- ✅ **Логировать для админа** (нужно исправлять)
- ✅ После N попыток: "Системная ошибка, попробуйте позже"

**Обработка**: `classify_kie_error()` → `'unknown'` → retry + log

---

## 📊 ТАБЛИЦА ДЕЙСТВИЙ

| Ошибка | Тип | Retry? | Notify User? | Refund? |
|--------|-----|--------|--------------|---------|
| KIE timeout | Transient | ✅ YES | ❌ NO | ❌ NO |
| sendVideo timeout | Transient | ✅ YES | ❌ NO | ❌ NO |
| Rate limit 429 | Transient | ✅ YES | ❌ NO | ❌ NO |
| Service 503 | Transient | ✅ YES | ❌ NO | ❌ NO |
| Photo too dark | User error | ❌ NO | ✅ YES | ✅ YES |
| No product visible | User error | ❌ NO | ✅ YES | ✅ YES |
| Invalid image | User error | ❌ NO | ✅ YES | ✅ YES |
| DB connection error | System | ✅ YES (N times) | ✅ After N | ✅ YES |
| API crash | System | ✅ YES (N times) | ✅ After N | ✅ YES |

---

## 💬 USER MESSAGES

### For Transient Errors (что писать ЕСЛИ надо):
**После 5 попыток, если еще не готово:**
```
⏳ Генерация занимает дольше обычного...

Sora 2 сейчас загружена 🔥
Я продолжу пытаться, не переживайте!

Если ошибка будет через 5 минут - попробуем еще раз.
```

**На sendVideo timeout (после 3 попыток):**
```
🌐 Ошибка сети при отправке видео.

Видео готово, но Telegram сейчас недоступен.
Кредиты возвращены ↩️

Попробуйте еще раз в меню.
```

### For User Errors:
```
❌ Фото не подходит для генерации видео

Возможные причины:
• Фото слишком темное
• Товар не виден четко
• Фото очень маленькое

💡 Совет: покажи товар крупнее при хорошем освещении

🔄 Попробуй еще раз (кредиты возвращены)
```

### For System Errors:
```
⚠️ Системная ошибка

Наши серверы сейчас переживают трудные времена 😅

Кредиты возвращены ↩️
Попробуйте через 5 минут.

Если ошибка повторится - напишите @support
```

---

## 🎯 РЕАЛЬНАЯ СТРАТЕГИЯ

### What We Should Do:

1. **No user notification for temporary errors**
   - Just retry silently
   - User sees "Generating... please wait" (already there)
   - System retries in background

2. **Notify only for user errors**
   - Classifier shows "bad_image" / "no_product" / etc
   - Send specific message to user
   - Refund credits
   - Suggest retry

3. **Notify after N failed system errors**
   - Retry 3-5 times
   - If still failing: notify user
   - Refund credits
   - Log for admin

---

## 🚀 IMPLEMENTATION PLAN

### Current State:
```python
# In video_processor.py - KIE generation loop
try:
    kie_task = create_task_sora_i2v(prompt, image_url)
    info = poll_record_info(kie_task, timeout=600)
    video_url = find_video_url(info)
    break  # Success
except Exception as e:
    # ❓ What to do here?
    # Currently: just retry
    attempt += 1
    continue
```

### What We Need:
```python
try:
    kie_task = create_task_sora_i2v(prompt, image_url)
    info = poll_record_info(kie_task, timeout=600)
    video_url = find_video_url(info)
    break  # Success
except Exception as e:
    error_type = classify_kie_error(str(e))  # ✅ USE CLASSIFIER
    
    if error_type == 'user_error':
        # DON'T retry
        await refund_credit(tg_user_id, CREDIT_COST)
        await send_user_message(tg_user_id, get_user_error_message(e))
        break  # Exit loop - don't retry
        
    elif error_type == 'transient':
        # Retry silently
        attempt += 1
        if attempt < MAX_ATTEMPTS:
            continue
        else:
            # Too many retries - give up
            await refund_credit(tg_user_id, CREDIT_COST)
            await send_user_message(tg_user_id, "System overloaded, please retry later")
            break
            
    else:  # unknown
        # Retry and log
        logger.error(f"Unknown error: {e}")
        attempt += 1
        if attempt < MAX_ATTEMPTS:
            continue
        else:
            await refund_credit(tg_user_id, CREDIT_COST)
            await send_user_message(tg_user_id, "System error, please retry")
            break
```

---

## 📋 MESSAGES USERS WILL SEE

### Scenario 1: Bad Photo
```
❌ Фото не подходит для генерации видео

Возможные причины:
• Фото слишком темное
• Товар не виден четко

💳 Кредиты возвращены (1 вернулся в баланс)

🔄 Попробуй еще раз
```

### Scenario 2: Too Many Timeouts (Sora overloaded)
```
⏳ Генерация заняла очень долго

Sora 2 сейчас очень загружена 🔥

💳 Кредиты возвращены

🔄 Попробуй позже (серверы отдохнут за 30 мин)
```

### Scenario 3: Send Timeout
```
✅ Видео готово!

🌐 Но ошибка при отправке в Telegram

💳 Кредиты возвращены (1 вернулся в баланс)

🔄 Попробуй еще раз - может в следующий раз пройдет
```

---

## ✨ SUMMARY

### What Changes:
1. **Transient errors**: Silent retry (NO messages)
2. **User errors**: Show message + refund
3. **System errors after N retries**: Show message + refund + log

### What Stays Same:
- Retry logic (already works)
- 3 retries for send
- 5 retries for generation

### User Impact:
- ✅ No spam messages for normal timeouts
- ✅ Clear message ONLY when something is wrong with photo
- ✅ Clear message ONLY after multiple retry failures
- ✅ Credits always refunded on ANY failure

---

## 🎯 IMPLEMENTATION PRIORITY

**What's critical to implement**:
1. Use `classify_kie_error()` to detect user_error vs transient
2. For user_error: refund + message
3. For transient: silent retry (maybe message after 5 retries)

**What's optional**:
- Pretty error messages (can be simple)
- Retry buttons (can just tell them to click "Generate Again")
- Detailed logging (nice to have)

**Time to implement**: 1 hour for core logic
