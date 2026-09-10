#!/bin/sh
# Landfall — safe close-out (PRD E13.11 / §4.15).
#
#   scripts/teardown.sh [BACKUP_DIR]
#
# Exports EVERY engagement (blobs + SQL) to a retained directory, checksums the
# archive, and ONLY THEN runs `azd down --purge`. If the export fails, is empty,
# or any engagement fails to export, it stops before touching the deployment —
# no silent data loss.
#
# The backup it writes is the input to `scripts/rehydrate.sh`. Keep it.
set -eu

BACKUP="${1:-_closeout/$(date -u +%Y%m%dT%H%M%SZ)}"

command -v azd >/dev/null 2>&1 || { echo "!! azd not on PATH"; exit 1; }
command -v az  >/dev/null 2>&1 || { echo "!! az not on PATH"; exit 1; }

echo "==> Loading azd environment"
eval "$(azd env get-values | sed 's/^/export /')"
RG="$(azd env get-value AZURE_RESOURCE_GROUP)"
[ -n "$RG" ] || { echo "!! no AZURE_RESOURCE_GROUP in the azd env — nothing to tear down"; exit 1; }

if ! az group show -n "$RG" >/dev/null 2>&1; then
  echo "==> $RG does not exist — already torn down. Nothing to do."
  exit 0
fi

echo "==> Exporting every engagement to $BACKUP  (blobs + SQL)"
python scripts/export_all.py --out "$BACKUP" --sql

MANIFEST="$BACKUP/manifest.json"
[ -f "$MANIFEST" ] || { echo "!! $MANIFEST not written — ABORT, not tearing down"; exit 1; }

read_count() { python -c "import json,sys;d=json.load(open(sys.argv[1]));print(len(d.get('$2',[])))" "$MANIFEST"; }
EXPORTED="$(read_count "$MANIFEST" engagements)"
FAILED="$(read_count "$MANIFEST" failed)"
echo "==> Exported $EXPORTED engagement(s); $FAILED failed"
[ "$FAILED" -eq 0 ] || { echo "!! $FAILED engagement(s) failed to export — ABORT"; exit 1; }
[ "$EXPORTED" -gt 0 ] || echo "   (no engagements found — the deployment held no client data)"

echo "==> Checksumming the archive"
( cd "$BACKUP" && { sha256sum ./*.landfall.zip 2>/dev/null || shasum -a 256 ./*.landfall.zip 2>/dev/null || true; } > SHA256SUMS )
cat "$BACKUP/SHA256SUMS" 2>/dev/null || true

echo
echo "==> Export OK. Tearing down $RG with --purge in 10s. Ctrl-C to abort."
sleep 10
azd down --force --purge

if az group show -n "$RG" >/dev/null 2>&1; then
  echo "!! $RG still exists after 'azd down --purge' — teardown INCOMPLETE, check the portal"
  exit 1
fi

echo
echo "==> $RG destroyed. Meter stopped."
echo "    Backup: $BACKUP  ($EXPORTED engagement(s))"
echo "    Bring it back with:  scripts/rehydrate.sh $BACKUP"
