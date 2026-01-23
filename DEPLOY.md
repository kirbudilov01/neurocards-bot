# 🚀 Быстрый деплой на VPS

## 1. Подготовка сервера

```bash
# SSH на сервер
ssh root@your-server-ip

# Обновить систему
apt update && apt upgrade -y

# Установить Docker
curl -fsSL https://get.docker.com | sh

# Установить Docker Compose
apt install docker-compose -y
```

## 2. Клонирование и настройка

```bash
git clone https://github.com/kirbudilov01/neurocards-bot.git
cd neurocards-bot
cp .env.docker .env
nano .env
```

Настройте `.env`:

```env
BOT_TOKEN=ваш_bot_token
PUBLIC_BASE_URL=https://your-domain.com
POSTGRES_PASSWORD=secure_password
KIE_API_KEY=key1,key2,key3,key4,key5
OPENAI_API_KEY=your_key
WORKER_REPLICAS=5
```

## 3. Запуск

```bash
docker-compose up -d
docker-compose logs -f
```

## 4. Масштабирование

```bash
# Увеличить до 20 воркеров
docker-compose up --scale worker=20 -d
```

Готово! 🎉
