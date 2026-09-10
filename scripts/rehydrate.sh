#!/bin/sh
# Landfall — rehydrate a torn-down deployment (PRD E13.11 / §4.15).
#
#   scripts/rehydrate.sh <BACKUP_DIR> [engagement-id ...]
#
# 1. asserts the resource group is GONE (this is not an update path — use
#    `azd deploy` for that; `azd up` on a live env re-runs postprovision, which
#    DROPs the SQL schema).
# 2. `azd up` — provisions + deploys the FULL stack. For the stack to come back
#    complete you must first have set, in the azd env:
#       azd env set DEPLOY_DRAWIO true                 # ca-drawio (PNG embed)
#       azd env set WEB_AUTH_CLIENT_ID <app-id>        # ca-web Easy Auth
#       azd env set --secret WEB_AUTH_CLIENT_SECRET    # (paste the secret)
#    These persist in .azure/<env>/ across a teardown, so you set them once.
# 3. re-versions the Foundry agent (`create_agent.py`).
# 4. prints how to re-import the engagements from BACKUP_DIR (the import API is
#    behind Easy Auth, so it is a dashboard action, not a curl).
set -eu

BACKUP="${1:?usage: scripts/rehydrate.sh <BACKUP_DIR> [engagement-id ...]}"
shift || true
[ -f "$BACKUP/manifest.json" ] || { echo "!! $BACKUP/manifest.json not found"; exit 1; }

command -v azd >/dev/null 2>&1 || { echo "!! azd not on PATH"; exit 1; }

RG="$(azd env get-value AZURE_RESOURCE_GROUP 2>/dev/null || echo '')"
if [ -n "$RG" ] && az group show -n "$RG" >/dev/null 2>&1; then
  echo "!! $RG already exists. rehydrate is for a torn-down environment."
  echo "   For a code update use:  azd deploy api|web|calc|drawio"
  exit 1
fi

# surface the stack-completeness switches before the long provision
DD="$(azd env get-value DEPLOY_DRAWIO 2>/dev/null || echo 'false')"
WA="$(azd env get-value WEB_AUTH_CLIENT_ID 2>/dev/null || echo '')"
echo "==> Stack switches:  DEPLOY_DRAWIO=$DD  WEB_AUTH_CLIENT_ID=$( [ -n "$WA" ] && echo set || echo 'EMPTY (no web auth)')"
[ "$DD" = "true" ] || echo "   (ca-drawio will NOT be deployed — 'azd env set DEPLOY_DRAWIO true' then re-run to include it)"

echo "==> azd up  (full stack; ~8-12 min cold)"
azd up

echo "==> Re-versioning the Foundry agent"
python scripts/create_agent.py || echo "   (create_agent.py failed — run it by hand once the env is loaded)"

echo "==> Post-deploy smoke (+ cold-start timing)"
python scripts/smoke.py --cold || echo "   (smoke reported issues — inspect above)"

WEB="$(azd env get-value SERVICE_WEB_URI 2>/dev/null || echo '')"
echo
echo "==> Stack is back: $WEB"
echo "    Re-import engagements from $BACKUP — the import API is behind Easy Auth, so:"
echo "      open $WEB  ->  the  ^ import  button  ->  pick each *.landfall.zip"
ls "$BACKUP"/*.landfall.zip 2>/dev/null | sed 's/^/        /' || true
if [ "$#" -gt 0 ]; then echo "    (you asked for: $*)"; fi
