# Stop FinAlly. The finally-data volume (database) is kept.
docker rm -f finally *> $null
Write-Host 'FinAlly stopped (data volume finally-data preserved)'
