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

@description('Entra app-registration client id for ca-web Easy Auth (E8.2). Empty = a fresh deploy has NO web auth. Set WEB_AUTH_CLIENT_ID + WEB_AUTH_CLIENT_SECRET to manage it as IaC — see DEPLOY.md.')
param webAuthClientId string = ''
@secure()
param webAuthClientSecret string = ''

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
    webAuthClientId: webAuthClientId
    webAuthClientSecret: webAuthClientSecret
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
