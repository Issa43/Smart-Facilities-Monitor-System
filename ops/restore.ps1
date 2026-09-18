param(
  [Parameter(Mandatory = $true)][string]$BackupDirectory,
  [Parameter(Mandatory = $true)][string]$Manifest,
  [string]$ProjectName = 'sflms-restore-verify',
  [string]$DockerPath = $env:DOCKER_EXE,
  [string]$BackendImage = 'sflms-backend:latest'
)

$ErrorActionPreference = 'Stop'
if ($ProjectName -notlike 'sflms-restore-*') { throw 'Restore project name must start with sflms-restore-.' }
if ($env:RESTORE_CONFIRM -ne $ProjectName) { throw 'RESTORE_CONFIRM must exactly match the disposable restore project name.' }
if (-not $env:BACKUP_ENCRYPTION_PASSPHRASE -or $env:BACKUP_ENCRYPTION_PASSPHRASE.Length -lt 20) {
  throw 'BACKUP_ENCRYPTION_PASSPHRASE must contain at least 20 characters.'
}
$docker = if ($DockerPath) { $DockerPath } else { (Get-Command docker.exe -ErrorAction Stop).Source }
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$backupRoot = (Resolve-Path $BackupDirectory).Path
$metadata = Get-Content -LiteralPath (Join-Path $backupRoot $Manifest) | ConvertFrom-Json
$dbEncrypted = Join-Path $backupRoot $metadata.database
$mediaEncrypted = Join-Path $backupRoot $metadata.media
foreach ($file in @($dbEncrypted, $mediaEncrypted)) {
  $expected = (Get-Content -LiteralPath "$file.sha256").Trim()
  $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $file).Hash
  if ($actual -ne $expected) { throw "Backup checksum mismatch: $file" }
}

$work = Join-Path $env:TEMP "sflms-restore-$([guid]::NewGuid().ToString('N'))"
[System.IO.Directory]::CreateDirectory($work) | Out-Null
$env:RESTORE_WORKDIR = $work
Push-Location $root
try {
  & $docker compose -p $ProjectName -f docker-compose.yml -f docker-compose.restore.yml up -d --no-build postgres redis
  $postgresId = (& $docker compose -p $ProjectName -f docker-compose.yml -f docker-compose.restore.yml ps -q postgres).Trim()
  if (-not $postgresId) { throw 'Disposable restore PostgreSQL container did not start.' }

  foreach ($pair in @(@($dbEncrypted, 'database.dump'), @($mediaEncrypted, 'media.tar.gz'))) {
    $source, $name = $pair
    & $docker run --rm --entrypoint python `
      -e "BACKUP_ENCRYPTION_PASSPHRASE=$env:BACKUP_ENCRYPTION_PASSPHRASE" `
      -v "${root}:/app:ro" -v "${backupRoot}:/backup:ro" -v "${work}:/work" `
      $BackendImage /app/ops/backup_crypto.py decrypt "/backup/$(Split-Path $source -Leaf)" "/work/$name"
  }

  & $docker cp (Join-Path $work 'database.dump') "${postgresId}:/tmp/database.dump"
  & $docker exec $postgresId sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner /tmp/database.dump'

  & $docker compose -p $ProjectName -f docker-compose.yml -f docker-compose.restore.yml run --rm --no-deps --entrypoint tar backend -xzf /restore/media.tar.gz -C /app
  & $docker compose -p $ProjectName -f docker-compose.yml -f docker-compose.restore.yml up -d --no-build backend
  & $docker compose -p $ProjectName -f docker-compose.yml -f docker-compose.restore.yml exec backend python manage.py check
  & $docker compose -p $ProjectName -f docker-compose.yml -f docker-compose.restore.yml exec backend python manage.py shell -c "from django.contrib.auth import get_user_model; from apps.projects.models import Project; print({'users': get_user_model().objects.count(), 'projects': Project.objects.count()})"
} finally {
  Pop-Location
  Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
  Remove-Item Env:RESTORE_WORKDIR -ErrorAction SilentlyContinue
}

Write-Output "Restore verification completed in disposable project: $ProjectName"
