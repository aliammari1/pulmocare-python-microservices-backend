#!/bin/bash
# Registry backup script

BACKUP_DIR="/backup/registry"
DATE=$(date +%Y%m%d-%H%M%S)
BACKUP_FILE="registry-backup-$DATE.tar.gz"

mkdir -p "$BACKUP_DIR"

# Backup registry data
tar -czf "$BACKUP_DIR/$BACKUP_FILE" \
    --exclude='*.log' \
    data/ certs/ auth/ config/

echo "Backup created: $BACKUP_DIR/$BACKUP_FILE"
