#!/bin/sh
# Landfall postprovision - runs after `azd provision`, before `azd deploy`.
# Idempotent: safe to re-run.
set -eu

echo "==> Loading azd environment"
eval "$(azd env get-values | sed 's/^/export /')"
export AZURE_SUBSCRIPTION_ID="$(azd env get-value AZURE_SUBSCRIPTION_ID)"

echo "==> Installing helper dependencies"
python -m pip install --quiet --disable-pip-version-check -r scripts/requirements.txt

echo "==> Applying SQL schema + read-only grant (Python; no sqlcmd needed)"
python scripts/apply_sql.py

echo "==> Building the AI Search index pipeline"
python scripts/setup_search.py

echo "==> Creating the Foundry agent"
AGENT_LINE="$(python scripts/create_agent.py)"
AGENT_ID="${AGENT_LINE#AGENT_ID=}"
echo "   agent: $AGENT_ID"
azd env set AGENT_ID "$AGENT_ID"

echo "==> Pushing AGENT_ID to the running services"
az functionapp config appsettings set -g "$AZURE_RESOURCE_GROUP" -n "$SERVICE_API_NAME" \
  --settings "AGENT_ID=$AGENT_ID" --output none
az containerapp update -g "$AZURE_RESOURCE_GROUP" -n "$SERVICE_WEB_NAME" \
  --set-env-vars "AGENT_ID=$AGENT_ID" --output none

echo "==> postprovision complete"
