targetScope = 'subscription'

@minLength(1)
@maxLength(32)
@description('Name of the azd environment - used to derive the resource group and resource names')
param environmentName string

@description('Primary location for all resources')
param location string

@description('Object id of the user or service principal running the deployment (azd sets AZURE_PRINCIPAL_ID). Used for data-plane role assignments so the postprovision scripts can run.')
param principalId string = ''

@description('Model + version for the chat model deployment')
param chatModelName string = 'gpt-4o'
param chatModelVersion string = '2024-11-20'

@description('Model + version for the embedding model deployment')
param embeddingModelName string = 'text-embedding-3-small'
param embeddingModelVersion string = '1'

@description('TPM (thousands) cap for each model deployment - doubles as a spend brake')
param modelCapacity int = 30

@description('Chat-UI container image; azd populates SERVICE_WEB_IMAGE_NAME after the first deploy')
param webImageName string = ''

@description('ca-calc (Pricing Calculator driver) image; azd populates SERVICE_CALC_IMAGE_NAME after the first deploy')
param calcImageName string = ''

@description('Foundry agent name; the postprovision hook stores AGENT_ID in the azd env')
param agentId string = ''

@description('Turn on Function App EasyAuth so query_inventory is not anonymous (azd env set ENABLE_FUNCTION_AUTH true)')
param enableFunctionAuth bool = false

@description('Entra client id the Function App accepts tokens for when auth is on (azd env set FUNCTION_AUTH_CLIENT_ID ...)')
param functionAuthClientId string = ''

@description('Optional: restrict Function App EasyAuth to these caller client ids, e.g. the Foundry MSI (azd env set FUNCTION_AUTH_ALLOWED_CLIENT_IDS ...)')
param functionAuthAllowedClientIds array = []

@description('Deployment tier. free = Free-tier / Free-offer SKUs (default, ~$5-15/mo, auto-pause, no SLA). prod = paid SKUs with SLAs, no free-limit cap, no cold start on the web app (~$350-450/mo). One switch; see DEPLOY.md section "Deployment tiers" for the per-resource cost delta. azd env set DEPLOYMENT_TIER prod')
@allowed(['free', 'prod'])
param deploymentTier string = 'free'

@description('Email for the answer-quality alert (E9.4 — Function tool error rate > 5% over 15 min). Empty = the answer-quality workbook is still deployed, but no alert / action group. azd env set ALERT_EMAIL you@example.com')
param alertEmail string = ''

@description('Monthly cost budget for this deployment (E13.4 / §4.15), in the SUBSCRIPTION BILLING CURRENCY (not necessarily USD — `python scripts/cost.py` prints yours). A resource-group Cost Management budget with actual-50%, actual-80% and forecast-100% alerts to ALERT_EMAIL (if set) and always the RG Owner. 0 disables it. Default 50 (fine for a USD sub; on e.g. an INR sub set ~4200 for a $50 target). azd env set MONTHLY_BUDGET 50')
param monthlyBudget int = 50

@description('First day of the current month (yyyy-MM-01) — the Cost Management budget start date must be the 1st. Leave as the default.')
param budgetStartDate string = utcNow('yyyy-MM-01')

@description('Log Analytics daily ingestion cap in GB (E13.4) — a runaway-telemetry brake. "-1" = uncapped (the prod tier always uncaps). Default 0.5. azd env set LOG_ANALYTICS_DAILY_CAP_GB 1')
param logAnalyticsDailyCapGb string = '0.5'

@description('ca-calc always-on replicas (E13.4 / §4.15). 1 (default) = the POE queue worker is always running while the stack is up (a few $/month; the ACA free grant covers most of it). 0 = cheaper but a POE run may sit unprocessed — KEDA queue scale-up on managed-identity auth did not work in C25b. azd env set CALC_MIN_REPLICAS 0')
param calcMinReplicas int = 1

@description('Entra app-registration client id for ca-web Easy Auth (E8.2). Empty = a fresh deploy has NO web auth. Set WEB_AUTH_CLIENT_ID + WEB_AUTH_CLIENT_SECRET to manage it as IaC — see DEPLOY.md.')
param webAuthClientId string = ''
@secure()
param webAuthClientSecret string = ''

@description('Deploy the ca-drawio SVG->PNG rasteriser as part of `azd up` (E11.22 / C27b / E13.11). false (default) = a fresh deploy is byte-identical to today (the diagram still ships as .drawio + .svg; only the .png embed in .pptx/.docx is absent). true = a fresh `azd up` / rehydrate reproduces the full stack. azd env set DEPLOY_DRAWIO true')
param deployDrawio bool = false
@description('ca-drawio container image — azd sets SERVICE_DRAWIO_IMAGE_NAME after the first build.')
param drawioImageName string = ''
@description('Shared key the Function sends to ca-drawio (X-Drawio-Key). Empty = derived deterministically from the resource token, so a fresh RG regenerates a matching pair for the app secret and the Function env var.')
param drawioKey string = ''

var abbrs = loadJsonContent('./abbreviations.json')
var resourceToken = toLower(uniqueString(subscription().id, environmentName, location))
var tags = { 'azd-env-name': environmentName }

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: '${abbrs.resourcesResourceGroups}${environmentName}'
  location: location
  tags: tags
}

module resources './resources.bicep' = {
  name: 'resources'
  scope: rg
  params: {
    location: location
    tags: tags
    resourceToken: resourceToken
    abbrs: abbrs
    principalId: principalId
    chatModelName: chatModelName
    chatModelVersion: chatModelVersion
    embeddingModelName: embeddingModelName
    embeddingModelVersion: embeddingModelVersion
    modelCapacity: modelCapacity
    webImageName: webImageName
    calcImageName: calcImageName
    agentId: agentId
    enableFunctionAuth: enableFunctionAuth
    functionAuthClientId: functionAuthClientId
    functionAuthAllowedClientIds: functionAuthAllowedClientIds
    deploymentTier: deploymentTier
    alertEmail: alertEmail
    monthlyBudget: monthlyBudget
    budgetStartDate: budgetStartDate
    logAnalyticsDailyCapGb: logAnalyticsDailyCapGb
    calcMinReplicas: calcMinReplicas
    webAuthClientId: webAuthClientId
    webAuthClientSecret: webAuthClientSecret
    deployDrawio: deployDrawio
    drawioImageName: drawioImageName
    drawioKey: empty(drawioKey) ? uniqueString(resourceToken, 'drawio-render') : drawioKey
  }
}

// ---- outputs consumed by azd (.azure/<env>/.env) and the postprovision scripts ----
output AZURE_LOCATION string = location
output AZURE_TENANT_ID string = tenant().tenantId
output AZURE_RESOURCE_GROUP string = rg.name

output AZURE_STORAGE_ACCOUNT string = resources.outputs.storageAccountName
output AZURE_STORAGE_BLOB_ENDPOINT string = resources.outputs.storageBlobEndpoint

output AZURE_SEARCH_ENDPOINT string = resources.outputs.searchEndpoint
output AZURE_SEARCH_INDEX_NAME string = 'landfall-docs'

output AZURE_OPENAI_ENDPOINT string = resources.outputs.openAiEndpoint
output AZURE_OPENAI_CHAT_DEPLOYMENT string = chatModelName
output AZURE_OPENAI_EMBEDDING_DEPLOYMENT string = embeddingModelName

output FOUNDRY_PROJECT_ENDPOINT string = resources.outputs.foundryProjectEndpoint
output FOUNDRY_ACCOUNT_NAME string = resources.outputs.foundryAccountName

output AZURE_SQL_SERVER_FQDN string = resources.outputs.sqlServerFqdn
output AZURE_SQL_DATABASE string = resources.outputs.sqlDatabaseName

output SERVICE_API_NAME string = resources.outputs.functionAppName
output AZURE_EVENTGRID_SYSTEM_TOPIC string = resources.outputs.eventGridSystemTopicName
output SERVICE_WEB_NAME string = resources.outputs.containerAppName
output SERVICE_WEB_URI string = resources.outputs.containerAppUri

output AZURE_CONTAINER_REGISTRY_ENDPOINT string = resources.outputs.containerRegistryLoginServer
output AZURE_USER_ASSIGNED_IDENTITY_CLIENT_ID string = resources.outputs.uamiClientId
output AZURE_USER_ASSIGNED_IDENTITY_NAME string = resources.outputs.uamiName
output AZURE_USER_ASSIGNED_IDENTITY_PRINCIPAL_ID string = resources.outputs.uamiPrincipalId
