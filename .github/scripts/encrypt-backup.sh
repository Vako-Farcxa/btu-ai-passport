#!/usr/bin/env bash
# Packs a backup folder into one tar.gz and encrypts it with AES-256 (OpenSSL, PBKDF2 key
# derivation, random salt). The passphrase comes from the BACKUP_PASSPHRASE environment
# variable, never from an argument, so it does not show up in a process list or a log.
# After encrypting it decrypts the file again and lists it, so a broken file fails the job
# now and not on the day someone needs the backup.
#
# Usage: BACKUP_PASSPHRASE=... encrypt-backup.sh FOLDER OUTPUT.tar.gz.enc
# Used by .github/workflows/backup.yml. Undo with decrypt-backup.sh.
set -euo pipefail

folder="${1:?usage: encrypt-backup.sh FOLDER OUTPUT.enc}"
output="${2:?usage: encrypt-backup.sh FOLDER OUTPUT.enc}"
: "${BACKUP_PASSPHRASE:?BACKUP_PASSPHRASE is not set}"
if [ "${#BACKUP_PASSPHRASE}" -lt 16 ]; then
  echo "::error::BACKUP_PASSPHRASE must be at least 16 characters" >&2
  exit 1
fi
[ -f "$folder/manifest.json" ] || { echo "No manifest.json in $folder" >&2; exit 1; }

# Keep these options in step with decrypt-backup.sh and docs/RESTORE.md.
tar -czf - -C "$folder" . \
  | openssl enc -aes-256-cbc -pbkdf2 -iter 600000 -salt -pass env:BACKUP_PASSPHRASE -out "$output"

openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 -pass env:BACKUP_PASSPHRASE -in "$output" \
  | tar -tzf - | grep -q '^\./manifest.json$' \
  || { echo "The encrypted file did not decrypt back to a backup" >&2; exit 1; }

echo "Encrypted backup written: $(basename "$output") ($(wc -c < "$output") bytes)"
