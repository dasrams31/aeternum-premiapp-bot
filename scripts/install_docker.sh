#!/usr/bin/env bash
# ==============================================================================
# Aeternum PremiApp Bot - Docker One-Click Installer
# ==============================================================================

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_DIR}"

echo "🐳 Memulai Setup Aeternum PremiApp Bot via Docker..."

# Pastikan file .env ada
if [ ! -f ".env" ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env
fi

# Build dan jalankan container
if command -v docker-compose &> /dev/null; then
    docker-compose down || true
    docker-compose up -d --build
else
    docker compose down || true
    docker compose up -d --build
fi

echo "✅ Docker container berhasil dijalankan!"
echo "Cek status container: docker ps"
echo "Cek log bot: docker logs -f aeternum_bot"
