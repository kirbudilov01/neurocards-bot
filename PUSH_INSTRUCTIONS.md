# 📤 ИНСТРУКЦИЯ ПО ДЕПЛОЮ

## Что сделано:
✅ Все критические баги исправлены
✅ Код протестирован локально  
✅ Commit создан (f016d11)
✅ Готово к push на main

## Что нужно сделать:

### 1. Запушить код на GitHub
```bash
cd /workspaces/neurocards-bot.worktrees/copilot-worktree-2026-01-22T18-12-59
git push origin copilot-worktree-2026-01-22T18-12-59:main
```

### 2. Задеплоить на VPS
```bash
ssh root@185.93.108.162
cd /root/neurocards-bot
git pull origin main
systemctl restart neurocards-bot
systemctl restart neurocards-worker@{1..5}
```

### 3. Проверить логи
```bash
# Bot
journalctl -u neurocards-bot -f

# Worker
journalctl -u neurocards-worker@1 -f
```

### 4. Протестировать в Telegram
- Отправь /start
- Сгенерируй реальное видео
- Проверь все сценарии ошибок
- Протести кнопки и flow

## Изменения в этом коммите:
1. Увеличен timeout KIE polling до 30 минут (было 6)
2. Созданы TEST_RESULTS.md и AUTONOMOUS_WORK_SUMMARY.md
3. Верифицированы все модули и imports

