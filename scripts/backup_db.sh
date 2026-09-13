#!/usr/bin/env bash
# ==============================================================================
# Aeternum PremiApp Bot - Automated Database Backup Script
# Melakukan dump database PostgreSQL, kompresi gzip, dan rotasi retensi (7 hari).
# ==============================================================================

set -e

BACKUP_DIR="${BACKUP_DIR:-/var/backups/aeternum_db}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/aeternum_db_${TIMESTAMP}.sql.gz"
RETENTION_DAYS=7

mkdir -p "${BACKUP_DIR}"

echo "📦 [$(date)] Memulai proses backup database PostgreSQL..."

# Jalankan dump via pg_dump atau via container docker
if command -v docker &> /dev/null && docker ps | grep -q aeternum_db; then
    echo "ℹ️ Mendeteksi PostgreSQL container: aeternum_db"
    docker exec -t aeternum_db pg_dump -U postgres aeternum_premiapp_db | gzip > "${BACKUP_FILE}"
elif command -v pg_dump &> /dev/null; then
    pg_dump -U postgres -d aeternum_premiapp_db | gzip > "${BACKUP_FILE}"
else
    echo "⚠️ pg_dump tidak ditemukan di host. Silakan pastikan Docker atau PostgreSQL client terpasang."
    exit 1
fi

echo "✅ [$(date)] Backup sukses disimpan di: ${BACKUP_FILE}"
echo "📊 Ukuran file backup: $(du -sh "${BACKUP_FILE}" | cut -f1)"

# Rotasi backup: Hapus file backup yang lebih tua dari RETENTION_DAYS
echo "🧹 Membersihkan backup lama (> ${RETENTION_DAYS} hari)..."
find "${BACKUP_DIR}" -type f -name "aeternum_db_*.sql.gz" -mtime +${RETENTION_DAYS} -exec rm -f {} \;

echo "🎉 [$(date)] Proses backup selesai dan aman."
