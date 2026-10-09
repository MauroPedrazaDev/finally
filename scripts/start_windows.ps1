# Start FinAlly in Docker. Pass -Build to force an image rebuild.
param([switch]$Build)

Set-Location (Join-Path $PSScriptRoot '..')

$Image = 'finally'
$Container = 'finally'
$Url = 'http://localhost:8000'

if (-not (Test-Path '.env')) {
    Copy-Item '.env.example' '.env'
    Write-Host 'Created .env from .env.example'
}

docker image inspect $Image *> $null
if ($Build -or $LASTEXITCODE -ne 0) {
    docker build -t $Image .
    if ($LASTEXITCODE -ne 0) { throw 'docker build failed' }
}

docker rm -f $Container *> $null

docker run -d --name $Container -v finally-data:/app/db -p 8000:8000 --env-file .env $Image | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'docker run failed' }

Write-Host "FinAlly is running at $Url"
try { Start-Process $Url } catch { }
