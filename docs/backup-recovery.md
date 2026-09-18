# Backup and Recovery

SFLMS backs up PostgreSQL plus both `media` and `protected_media`. Redis is a
broker/cache and is rebuilt rather than treated as the system of record.

## Backup

`ops/backup.ps1` performs a custom-format `pg_dump`, archives both media roots,
encrypts each artifact with streaming AES-256-GCM, derives keys with PBKDF2,
verifies authentication, and writes SHA-256 checksums plus a JSON manifest.
The destination is operator supplied, so it can be a mounted offsite/object
storage staging path. Retention defaults to 14 days and is scoped to files whose
names begin with `sflms-` in that destination.

```powershell
$env:BACKUP_ENCRYPTION_PASSPHRASE = '<secret-from-secret-manager>'
.\ops\backup.ps1 -Destination 'D:\offsite-staging\sflms' -RetentionDays 14
```

The passphrase is never written to a manifest or repository. A failed dump,
encryption, verification, or copy exits non-zero so the scheduler can alert.

## Restore

Restore is deliberately guarded. The Compose project name must start with
`sflms-restore-`, `RESTORE_CONFIRM` must match it exactly, checksums and GCM
authentication must pass, and the target uses fresh named volumes.

```powershell
$env:BACKUP_ENCRYPTION_PASSPHRASE = '<same-secret>'
$env:RESTORE_CONFIRM = 'sflms-restore-drill'
.\ops\restore.ps1 -BackupDirectory 'D:\offsite-staging\sflms' `
  -Manifest 'sflms-<timestamp>-manifest.json' -ProjectName 'sflms-restore-drill'
```

The restore script loads PostgreSQL and both media roots, starts an isolated
backend, runs Django checks, and reports record-count smoke evidence. Remove the
disposable project with its explicit name after inspection.

## Verification record

On 2026-08-25 an encrypted backup of the running development stack was restored
into `sflms-restore-verify`. AES-GCM verification, Django checks, and restored
record smoke checks passed (`users=4`, `projects=1`). The restore containers,
network, volumes, raw temporary files, and encrypted test artifacts were then
removed. This validates the mechanism; production RPO/RTO, offsite provider,
and legal retention remain deployment-owner decisions.

Never use a production Compose project as a restore target and never use
`docker compose down -v` without an explicitly disposable project name.
