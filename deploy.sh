#!/bin/bash

# Production deployment script for Railway/Docker

set -e

echo "🚀 Starting deployment..."

# Check if .env exists
if [ ! -f .env ]; then
    echo "❌ .env file not found. Copy from env.example and configure."
    exit 1
fi

# Build and deploy
echo "📦 Building Docker image..."
docker build -t support-chat:latest .

echo "🔍 Running health check..."
if ! curl -f http://localhost:8000/health > /dev/null 2>&1; then
    echo "⚠️  Health check failed, but continuing deployment..."
fi

echo "🎯 Deploying to production..."
docker-compose -f docker-compose.prod.yml up -d --build

echo "⏳ Waiting for service to be ready..."
sleep 10

# Final health check
for i in {1..30}; do
    if curl -f http://localhost:8000/health > /dev/null 2>&1; then
        echo "✅ Deployment successful! Service is healthy."
        exit 0
    fi
    echo "Waiting for service... ($i/30)"
    sleep 2
done

echo "❌ Deployment may have failed. Check logs with: docker-compose logs"
exit 1