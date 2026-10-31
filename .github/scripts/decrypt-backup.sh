#!/usr/bin/env bash
# Decrypts and unpacks a backup made by encrypt-backup.sh into FOLDER (created if needed).
# The passphrase is read from BACKUP_PASSPHRASE, or asked for when that is not set.
#
# Usage: decrypt-backup.sh BACKUP.tar.gz.enc FOLDER
set -euo pipefail

input="${1:?usage: decrypt-backup.sh BACKUP.enc FOLDER}"
folder="${2:?usage: decrypt-backup.sh BACKUP.enc FOLDER}"
if [ -z "${BACKUP_PASSPHRASE:-}" ]; then
  read -r -s -p "Backup passphrase: " BACKUP_PASSPHRASE
  echo
  export BACKUP_PASSPHRASE
fi

mkdir -p "$folder"
openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 -pass env:BACKUP_PASSPHRASE -in "$input" \
  | tar -xzf - -C "$folder"
[ -f "$folder/manifest.json" ] || { echo "Wrong passphrase or not a backup file" >&2; exit 1; }
echo "Unpacked into $folder"
