# Server Deployment Fix Guide

## Issues Identified
1. **docker-compose v1.29.2 bug** - KeyError: 'ContainerConfig' when recreating containers
2. **Redis replica misconfiguration** - Trying to sync with unreachable master (119.45.248.246:28653)
3. **Container networking issues** - DNS resolution failures between containers

## Fix Steps

### Step 1: Stop and Clean All Containers
```bash
cd /root/neurocards-bot
docker-compose down -v
docker system prune -f
```

### Step 2: Upgrade docker-compose (CRITICAL)
```bash
# Check current version
docker-compose --version

# If version is 1.29.x, upgrade to latest
sudo apt-get update
sudo apt-get install -y docker-compose-plugin

# Or use Docker's native compose
sudo apt-get install -y docker.io

# Verify upgrade
docker compose version
```

### Step 3: Verify .env File Has All Required Variables
```bash
cat /root/neurocards-bot/.env
```

Required variables:
```
BOT_TOKEN=<your_token>
POSTGRES_PASSWORD=<secure_password>
POSTGRES_USER=neurocards
WELCOME_VIDEO_FILE_ID=BAACAgIAAxkDAAILJGl5IaAMci6a4k8-M5eR44F0p3jbAAKKnQACbwzJS-5ozluLjT3wOAQ
STORAGE_TYPE=local
STORAGE_BASE_PATH=/app/storage
PUBLIC_BASE_URL=http://185.93.108.162:8080
```

### Step 4: Rebuild Docker Images
```bash
cd /root/neurocards-bot
docker-compose build --no-cache
```

### Step 5: Start Services with Proper Logging
```bash
# Start in foreground to see any errors
docker-compose up

# Or start in background
docker-compose up -d
sleep 15

# Check service status
docker ps -a
```

### Step 6: Verify Each Service
```bash
# Check database
docker logs neurocards-postgres | tail -30

# Check Redis
docker logs neurocards-redis | tail -30

# Check bot
docker logs neurocards-polling | tail -50

# Check worker
docker logs neurocards-worker-1 | tail -50
```

### Step 7: Test Connectivity Between Containers
```bash
# Test from polling bot to database
docker exec neurocards-polling ping neurocards-postgres

# Test from polling bot to redis
docker exec neurocards-polling redis-cli -h redis ping

# Test database initialization
docker exec neurocards-postgres psql -U neurocards -d neurocards -c "SELECT 1;"
```

## If docker-compose still fails with ContainerConfig error:

Try using Docker Compose v2:
```bash
docker compose --version
docker compose -f docker-compose.yml up -d
```

## If services still fail to connect:

### Restart Docker daemon:
```bash
sudo systemctl restart docker
sleep 5
docker-compose up -d
```

### Check Docker network:
```bash
docker network ls
docker network inspect neurocards-bot_neurocards
```

## Troubleshooting Commands

```bash
# View all container logs
docker-compose logs -f

# View specific service
docker-compose logs neurocards-postgres
docker-compose logs neurocards-redis
docker-compose logs neurocards-polling

# Check if ports are in use
lsof -i :5432
lsof -i :6379
lsof -i :8080

# Restart specific service
docker-compose restart neurocards-polling
docker-compose restart neurocards-redis
docker-compose restart neurocards-postgres
```

## Expected Healthy State

After fixes, you should see:
- `neurocards-postgres` - **healthy** ✓
- `neurocards-redis` - **healthy** ✓
- `neurocards-polling` - **running** ✓
- `neurocards-worker-1/2/3` - **running** ✓

All Redis logs should show: `The server is now ready to accept connections`
All PostgreSQL logs should show: `database system is ready to accept connections`
