#!/bin/bash
set -e
echo "🔨 Testing Docker builds..."
docker build -f Dockerfile.bot -t neurocards-bot:test .
docker build -f Dockerfile.worker -t neurocards-worker:test .
echo "✅ All builds successful!"
