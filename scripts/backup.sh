#!/bin/sh
# ══════════════════════════════════════════════════════════════════
#  蒙牛全产业链 AI 内生合规决策大脑 — 数据库自动备份脚本
#
#  功能:
#    - pg_dump 完整备份（gzip 压缩）
#    - 保留最近 BACKUP_RETENTION_DAYS 天的备份
#    - 备份文件命名: taxmind_YYYYMMDD_HHMMSS.sql.gz
#    - 失败时输出错误日志
#
#  环境变量:
#    PGHOST, PGUSER, PGPASSWORD, PGDATABASE
#    BACKUP_RETENTION_DAYS (默认 30)
# ══════════════════════════════════════════════════════════════════

set -e

BACKUP_DIR="${BACKUP_DIR:-/backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/taxmind_${TIMESTAMP}.sql.gz"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting backup..."

# 执行备份
pg_dump \
    --host="${PGHOST:-postgres}" \
    --username="${PGUSER:-taxmind}" \
    --dbname="${PGDATABASE:-taxmind}" \
    --no-password \
    --no-owner \
    --format=custom \
    --compress=9 \
    --file="${BACKUP_FILE}" 2>&1

if [ $? -eq 0 ]; then
    BACKUP_SIZE=$(du -h "${BACKUP_FILE}" | cut -f1)
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Backup successful: ${BACKUP_FILE} (${BACKUP_SIZE})"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Backup FAILED!" >&2
    exit 1
fi

# 清理过期备份
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Cleaning backups older than ${RETENTION_DAYS} days..."
find "${BACKUP_DIR}" -name "taxmind_*.sql.gz" -type f -mtime "+${RETENTION_DAYS}" -delete 2>&1 || true

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Backup job completed."
