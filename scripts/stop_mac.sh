#!/usr/bin/env bash
# Stop FinAlly. The finally-data volume (database) is kept.
docker rm -f finally >/dev/null 2>&1 || true
echo "FinAlly stopped (data volume finally-data preserved)"
