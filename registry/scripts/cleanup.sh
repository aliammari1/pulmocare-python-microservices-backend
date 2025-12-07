#!/bin/bash
# Registry cleanup script

# Remove old backups (keep last 7 days)
find /backup/registry -name "registry-backup-*.tar.gz" -mtime +7 -delete

# Remove old log files
find logs/ -name "*.log" -mtime +30 -delete

# Docker system cleanup
docker system prune -f --volumes

echo "Cleanup completed"
