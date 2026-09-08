#!/bin/sh
# Landfall postdeploy - wire the questions/ container to the `start` function via
# Event Grid. On the Flex Consumption plan a blob trigger must be driven by Event
# Grid, and the subscription's webhook URL needs the function app's
# `blobs_extension` system key, which only exists once `azd deploy` has published
# the function - hence postdeploy. Idempotent: safe to re-run.
set -eu

# Git Bash / MSYS rewrites a leading-slash arg like "/blobServices/..." into a
# Windows path ("C:/Program Files/Git/blobServices/...") before az sees it, which
# silently corrupts --subject-begins-with. Opt out of that conversion.
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL="*"

echo "==> Loading azd environment"
eval "$(azd env get-values | sed 's/^/export /')"

az extension add --name eventgrid --only-show-errors --yes >/dev/null 2>&1 || true

RG="$AZURE_RESOURCE_GROUP"
FUNC="$SERVICE_API_NAME"
TOPIC="$AZURE_EVENTGRID_SYSTEM_TOPIC"

echo "==> Fetching the blob-extension system key (waiting for the function host)"
KEY=""
i=0
while [ -z "$KEY" ] && [ $i -lt 20 ]; do
  KEY="$(az functionapp keys list -g "$RG" -n "$FUNC" --query 'systemKeys.blobs_extension' -o tsv 2>/dev/null || true)"
  [ -z "$KEY" ] && { i=$((i+1)); sleep 15; }
done
if [ -z "$KEY" ]; then
  echo "   ! blobs_extension key not available - the Storage extension may still be loading."
  echo "     Re-run:  azd hooks run postdeploy   (or see DEPLOY.md for the manual step)."
  exit 1
fi

BASE="https://${FUNC}.azurewebsites.net/runtime/webhooks/blobs"

echo "==> Creating/updating the 'landfall-questions' event subscription"
az eventgrid system-topic event-subscription create \
  --name landfall-questions \
  --system-topic-name "$TOPIC" \
  --resource-group "$RG" \
  --endpoint-type webhook \
  --endpoint "${BASE}?functionName=Host.Functions.start&code=${KEY}" \
  --included-event-types Microsoft.Storage.BlobCreated \
  --subject-begins-with "/blobServices/default/containers/questions/blobs/" \
  --max-delivery-attempts 30 \
  --event-ttl 1440 \
  --only-show-errors \
  --output none

echo "==> Creating/updating the 'landfall-inventory' event subscription"
az eventgrid system-topic event-subscription create \
  --name landfall-inventory \
  --system-topic-name "$TOPIC" \
  --resource-group "$RG" \
  --endpoint-type webhook \
  --endpoint "${BASE}?functionName=Host.Functions.ingest_blob&code=${KEY}" \
  --included-event-types Microsoft.Storage.BlobCreated \
  --subject-begins-with "/blobServices/default/containers/raw/blobs/engagements/" \
  --max-delivery-attempts 30 \
  --event-ttl 1440 \
  --only-show-errors \
  --output none

echo "==> Verifying the subscription filters"
for sub in landfall-questions landfall-inventory; do
  got="$(az eventgrid system-topic event-subscription show --name "$sub" \
    --system-topic-name "$TOPIC" --resource-group "$RG" \
    --query 'filter.subjectBeginsWith' -o tsv 2>/dev/null || true)"
  case "$got" in
    /blobServices/*) echo "   $sub: $got" ;;
    *) echo "   ! $sub subject filter looks wrong: '$got' - re-run with MSYS_NO_PATHCONV=1"; exit 1 ;;
  esac
done

echo "==> postdeploy complete - questions/*.xlsx triggers the batch runner;"
echo "    raw/inventory/* triggers the ingestion pipeline"
