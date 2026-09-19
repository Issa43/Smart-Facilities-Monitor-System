param(
  [Parameter(Mandatory = $true)][string]$Destination,
  [string]$ProjectName = 'sflms',
  [int]$RetentionDays = 14,
  [string]$DockerPath = $env:DOCKER_EXE
)

$ErrorActionPreference = 'Stop'
if (-not $env:BACKUP_ENCRYPTION_PASSPHRASE -or $env:BACKUP_ENCRYPTION_PASSPHRASE.Length -lt 20) {
  throw 'BACKUP_ENCRYPTION_PASSPHRASE must contain at least 20 characters.'
}
$docker = if ($DockerPath) { $DockerPath } else { (Get-Command docker.exe -ErrorAction Stop).Source }
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$target = [System.IO.Path]::GetFullPath($Destination)
[System.IO.Directory]::CreateDirectory($target) | Out-Null
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
$databaseRaw = Join-Path $target "sflms-$stamp-db.dump"
$databaseEncrypted = "$databaseRaw.enc"
$mediaEncrypted = Join-Path $target "sflms-$stamp-media.tar.gz.enc"

Push-Location $root
try {
  $postgresId = (& $docker compose -p $ProjectName -f docker-compose.yml ps -q postgres).Trim()
  $backendId = (& $docker compose -p $ProjectName -f docker-compose.yml ps -q backend).Trim()
  if (-not $postgresId -or -not $backendId) { throw 'PostgreSQL and backend containers must be running.' }

  & $docker exec $postgresId sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --file=/tmp/sflms-db.dump'
  & $docker cp "${postgresId}:/tmp/sflms-db.dump" $databaseRaw
  & $docker cp $databaseRaw "${backendId}:/tmp/sflms-db.dump"
  & $docker exec -e "BACKUP_ENCRYPTION_PASSPHRASE=$env:BACKUP_ENCRYPTION_PASSPHRASE" $backendId python /app/ops/backup_crypto.py encrypt /tmp/sflms-db.dump /tmp/sflms-db.dump.enc
  & $docker cp "${backendId}:/tmp/sflms-db.dump.enc" $databaseEncrypted

  & $docker exec $backendId tar -czf /tmp/sflms-media.tar.gz -C /app media protected_media
  & $docker exec -e "BACKUP_ENCRYPTION_PASSPHRASE=$env:BACKUP_ENCRYPTION_PASSPHRASE" $backendId python /app/ops/backup_crypto.py encrypt /tmp/sflms-media.tar.gz /tmp/sflms-media.tar.gz.enc
  & $docker cp "${backendId}:/tmp/sflms-media.tar.gz.enc" $mediaEncrypted

  foreach ($artifact in @($databaseEncrypted, $mediaEncrypted)) {
    & $docker cp $artifact "${backendId}:/tmp/verify.enc"
    & $docker exec -e "BACKUP_ENCRYPTION_PASSPHRASE=$env:BACKUP_ENCRYPTION_PASSPHRASE" $backendId python /app/ops/backup_crypto.py verify /tmp/verify.enc
    (Get-FileHash -Algorithm SHA256 -LiteralPath $artifact).Hash | Set-Content -LiteralPath "$artifact.sha256"
  }
  @{ created_at = $stamp; database = (Split-Path $databaseEncrypted -Leaf); media = (Split-Path $mediaEncrypted -Leaf); encryption = 'AES-256-GCM'; retention_days = $RetentionDays } |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $target "sflms-$stamp-manifest.json")

  Get-ChildItem -LiteralPath $target -File -Filter 'sflms-*' |
    Where-Object LastWriteTimeUtc -lt (Get-Date).ToUniversalTime().AddDays(-$RetentionDays) |
    Remove-Item -Force
} finally {
  Remove-Item -LiteralPath $databaseRaw -Force -ErrorAction SilentlyContinue
  if ($postgresId) { & $docker exec $postgresId rm -f /tmp/sflms-db.dump | Out-Null }
  if ($backendId) { & $docker exec -u root $backendId rm -f /tmp/sflms-db.dump /tmp/sflms-db.dump.enc /tmp/sflms-media.tar.gz /tmp/sflms-media.tar.gz.enc /tmp/verify.enc | Out-Null }
  Pop-Location
}

Write-Output "Encrypted backup completed: $stamp"
