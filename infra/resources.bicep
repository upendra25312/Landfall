@description('All Landfall resources, deployed into the azd resource group.')
param location string
param tags object
param resourceToken string
param abbrs object
param principalId string
param chatModelName string
param chatModelVersion string
param embeddingModelName string
param embeddingModelVersion string
param modelCapacity int

@description('Chat-UI container image. Empty on first provision (placeholder is used); azd sets SERVICE_WEB_IMAGE_NAME after the first deploy so re-provisioning keeps the real image.')
param webImageName string = ''

@description('Turn on Function App built-in auth (EasyAuth) so query_inventory is not anonymous. When true, set AGENT_TOOL_AUTH=managed and re-run create_agent.py so the agent calls it with its managed identity. /runtime is excluded so the Event Grid webhook + durable endpoints keep working.')
param enableFunctionAuth bool = false

@description('Entra app registration (client) id the Function App accepts tokens for, when enableFunctionAuth is true. Usually api://<function-app-name>.')
param functionAuthClientId string = ''

@description('Foundry agent name. Empty on first provision; the postprovision hook creates the agent and stores AGENT_ID in the azd env so re-provisioning keeps it wired to both services.')
param agentId string = ''

// ---------- built-in role definition ids ----------
var roles = {
  storageBlobDataOwner: 'b7e6dc6d-f1e8-4753-8033-0f276bb0955b'
  storageBlobDataReader: '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1'
  storageQueueDataContributor: '974c5e8b-45b9-4653-ba55-5f855dd0fb88'
  storageTableDataContributor: '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3'
  searchServiceContributor: '7ca78c08-252a-4471-8644-bb5ff32d4ba0'
  searchIndexDataContributor: '8ebe5a00-799e-43f5-93ac-243d3dce84a7'
  cognitiveServicesOpenAiUser: '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
  azureAiDeveloper: '64702f94-c441-49e6-a78b-ef80e0188fee'
  foundryUser: '53ca6127-db72-4b80-b1b0-d745d6d5456d' // new Foundry: invoke projects / prompt agents (Responses API)
  acrPull: '7f951dda-4ed3-4680-a7ca-43fe172d538d'
  keyVaultSecretsUser: '4633458b-17de-408a-b874-0445c86b69e6'
}

// ==================================================================
// Identity
// ==================================================================
resource uami 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${abbrs.managedIdentityUserAssignedIdentities}landfall-${resourceToken}'
  location: location
  tags: tags
}

// ==================================================================
// Monitoring
// ==================================================================
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${abbrs.operationalInsightsWorkspaces}${resourceToken}'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: '${abbrs.insightsComponents}${resourceToken}'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
  }
}

// ==================================================================
// Key Vault
// ==================================================================
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: '${abbrs.keyVaultVaults}${resourceToken}'
  location: location
  tags: tags
  properties: {
    sku: { family: 'A', name: 'standard' }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
  }
}

// ==================================================================
// Storage - ADLS Gen2 (hierarchical namespace) + containers
// ==================================================================
resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: '${abbrs.storageStorageAccounts}${resourceToken}'
  location: location
  tags: tags
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    isHnsEnabled: true
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    minimumTlsVersion: 'TLS1_2'
    networkAcls: { defaultAction: 'Allow', bypass: 'AzureServices' }
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
}

var containerNames = [
  'raw'          // client inventory + narrative docs land here (raw/inventory, raw/docs)
  'questions'    // RFP question sheets uploaded here trigger the batch runner
  'answers'      // answered workbooks + ingest logs
  'work'         // internal working copies for the Durable orchestration
  'deploymentpackage' // Flex Consumption zip-deploy target
]

resource containers 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = [for name in containerNames: {
  parent: blobService
  name: name
}]

// ==================================================================
// Azure AI Search - FREE tier (50 MB, no semantic ranker, no SLA)
// ==================================================================
resource search 'Microsoft.Search/searchServices@2024-06-01-preview' = {
  name: '${abbrs.searchSearchServices}${resourceToken}'
  location: location
  tags: tags
  sku: { name: 'free' }
  identity: { type: 'SystemAssigned' }
  properties: {
    replicaCount: 1
    partitionCount: 1
    hostingMode: 'default'
    semanticSearch: 'disabled'
    authOptions: { aadOrApiKey: { aadAuthFailureMode: 'http403' } }
  }
}

// ==================================================================
// Azure AI Foundry (AIServices account + project) + model deployments
// ==================================================================
resource foundry 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: '${abbrs.cognitiveServicesAccounts}${resourceToken}'
  location: location
  tags: tags
  kind: 'AIServices'
  sku: { name: 'S0' }
  identity: { type: 'SystemAssigned' }
  properties: {
    customSubDomainName: '${abbrs.cognitiveServicesAccounts}${resourceToken}'
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: false
    allowProjectManagement: true
  }
}

resource foundryProject 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' = {
  parent: foundry
  name: 'landfall'
  location: location
  tags: tags
  identity: { type: 'SystemAssigned' }
  properties: {
    displayName: 'Landfall Migration Estimator'
    description: 'Agentic migration-assessment and RFP-estimate workspace'
  }
}

resource chatDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: foundry
  name: chatModelName
  sku: { name: 'GlobalStandard', capacity: modelCapacity }
  properties: {
    model: { format: 'OpenAI', name: chatModelName, version: chatModelVersion }
    versionUpgradeOption: 'OnceNewDefaultVersionAvailable'
  }
}

resource embeddingDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: foundry
  name: embeddingModelName
  sku: { name: 'GlobalStandard', capacity: modelCapacity }
  dependsOn: [ chatDeployment ] // deployments must be created serially
  properties: {
    model: { format: 'OpenAI', name: embeddingModelName, version: embeddingModelVersion }
  }
}

// ==================================================================
// Azure SQL - FREE offer (serverless, auto-pause), Entra-only auth
// ==================================================================
resource sqlServer 'Microsoft.Sql/servers@2023-08-01-preview' = {
  name: '${abbrs.sqlServers}${resourceToken}'
  location: location
  tags: tags
  properties: {
    version: '12.0'
    minimalTlsVersion: '1.2'
    publicNetworkAccess: 'Enabled'
    administrators: {
      administratorType: 'ActiveDirectory'
      principalType: 'User'
      login: 'landfall-admin'
      sid: principalId
      tenantId: subscription().tenantId
      azureADOnlyAuthentication: true
    }
  }
}

resource sqlDatabase 'Microsoft.Sql/servers/databases@2023-08-01-preview' = {
  parent: sqlServer
  name: '${abbrs.sqlServersDatabases}landfall'
  location: location
  tags: tags
  sku: { name: 'GP_S_Gen5_2', tier: 'GeneralPurpose', family: 'Gen5', capacity: 2 }
  properties: {
    autoPauseDelay: 60
    minCapacity: json('0.5')
    maxSizeBytes: 34359738368
    useFreeLimit: true
    freeLimitExhaustionBehavior: 'AutoPause'
    zoneRedundant: false
  }
}

resource sqlFirewallAzure 'Microsoft.Sql/servers/firewallRules@2023-08-01-preview' = {
  parent: sqlServer
  name: 'AllowAllAzureServices'
  properties: { startIpAddress: '0.0.0.0', endIpAddress: '0.0.0.0' }
}

// ==================================================================
// Container Registry + Container Apps environment
// ==================================================================
resource acr 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' = {
  name: '${abbrs.containerRegistryRegistries}${resourceToken}'
  location: location
  tags: tags
  sku: { name: 'Basic' }
  properties: { adminUserEnabled: false }
}

resource containerEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${abbrs.appManagedEnvironments}${resourceToken}'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

// ==================================================================
// Chat UI - Azure Container App (scale to zero)
// ==================================================================
resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${abbrs.appContainerApps}web-${resourceToken}'
  location: location
  tags: union(tags, { 'azd-service-name': 'web' })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${uami.id}': {} }
  }
  properties: {
    managedEnvironmentId: containerEnv.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
      }
      registries: [
        { server: acr.properties.loginServer, identity: uami.id }
      ]
    }
    template: {
      containers: [
        {
          name: 'web'
          image: !empty(webImageName) ? webImageName : 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest' // placeholder until first azd deploy
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: [
            { name: 'FOUNDRY_PROJECT_ENDPOINT', value: '${foundry.properties.endpoint}api/projects/landfall' }
            { name: 'AZURE_CLIENT_ID', value: uami.properties.clientId }
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsights.properties.ConnectionString }
            { name: 'AGENT_ID', value: agentId } // seeded from azd env; postprovision refreshes it
          ]
        }
      ]
      scale: { minReplicas: 0, maxReplicas: 2 }
    }
  }
}

// ==================================================================
// Excel batch runner - Azure Functions (Flex Consumption), Durable
// ==================================================================
resource functionPlan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: '${abbrs.webServerFarms}${resourceToken}'
  location: location
  tags: tags
  kind: 'functionapp'
  sku: { name: 'FC1', tier: 'FlexConsumption' }
  properties: { reserved: true }
}

resource functionApp 'Microsoft.Web/sites@2023-12-01' = {
  name: '${abbrs.webSitesFunctions}${resourceToken}'
  location: location
  tags: union(tags, { 'azd-service-name': 'api' })
  kind: 'functionapp,linux'
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${uami.id}': {} }
  }
  properties: {
    serverFarmId: functionPlan.id
    httpsOnly: true
    functionAppConfig: {
      deployment: {
        storage: {
          type: 'blobContainer'
          value: '${storage.properties.primaryEndpoints.blob}deploymentpackage'
          authentication: {
            type: 'UserAssignedIdentity'
            userAssignedIdentityResourceId: uami.id
          }
        }
      }
      scaleAndConcurrency: {
        maximumInstanceCount: 40
        instanceMemoryMB: 2048
      }
      runtime: { name: 'python', version: '3.11' }
    }
    siteConfig: {
      appSettings: [
        { name: 'AzureWebJobsStorage__accountName', value: storage.name }
        { name: 'AzureWebJobsStorage__credential', value: 'managedidentity' }
        { name: 'AzureWebJobsStorage__clientId', value: uami.properties.clientId }
        { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsights.properties.ConnectionString }
        { name: 'AZURE_CLIENT_ID', value: uami.properties.clientId }
        // identity-based blob trigger source (connection prefix STORAGE_CONN)
        { name: 'STORAGE_CONN__blobServiceUri', value: storage.properties.primaryEndpoints.blob }
        { name: 'STORAGE_CONN__queueServiceUri', value: storage.properties.primaryEndpoints.queue }
        { name: 'STORAGE_CONN__credential', value: 'managedidentity' }
        { name: 'STORAGE_CONN__clientId', value: uami.properties.clientId }
        // app config consumed by function_app.py
        { name: 'STORAGE_URL', value: storage.properties.primaryEndpoints.blob }
        { name: 'FOUNDRY_PROJECT_ENDPOINT', value: '${foundry.properties.endpoint}api/projects/landfall' }
        { name: 'AGENT_ID', value: agentId } // seeded from azd env; postprovision refreshes it
        // config consumed by tools.py (query_inventory / vm_rightsize / azure_retail_prices)
        { name: 'AZURE_OPENAI_CHAT_DEPLOYMENT', value: chatModelName } // text-to-SQL model
        { name: 'AZURE_SQL_SERVER_FQDN', value: sqlServer.properties.fullyQualifiedDomainName }
        { name: 'AZURE_SQL_DATABASE', value: sqlDatabase.name }
        { name: 'QUERY_TIMEOUT_S', value: '20' } // query_inventory statement timeout (E8.3)
      ]
    }
  }
}

// EasyAuth for query_inventory (E8.2). Off by default; `azd env set ENABLE_FUNCTION_AUTH true`
// (and provide FUNCTION_AUTH_CLIENT_ID) turns it on. /runtime stays excluded so the Event
// Grid webhook and durable endpoints keep working; unauthenticated calls get 401.
resource functionAuth 'Microsoft.Web/sites/config@2023-12-01' = if (enableFunctionAuth) {
  parent: functionApp
  name: 'authsettingsV2'
  properties: {
    platform: { enabled: true }
    globalValidation: {
      requireAuthentication: true
      unauthenticatedClientAction: 'Return401'
      excludedPaths: [ '/runtime' ]
    }
    identityProviders: {
      azureActiveDirectory: {
        enabled: true
        registration: {
          openIdIssuer: '${environment().authentication.loginEndpoint}${subscription().tenantId}/v2.0'
          clientId: functionAuthClientId
        }
        validation: {
          allowedAudiences: [ functionAuthClientId ]
        }
      }
    }
  }
}

// ==================================================================
// Event Grid - Flex Consumption requires EventGrid as the blob-trigger
// source. System topic on the storage account -> the `start` function.
// ==================================================================
resource egSystemTopic 'Microsoft.EventGrid/systemTopics@2024-06-01-preview' = {
  name: '${abbrs.storageStorageAccounts}${resourceToken}-egst'
  location: location
  tags: tags
  identity: { type: 'SystemAssigned' }
  properties: {
    source: storage.id
    topicType: 'Microsoft.Storage.StorageAccounts'
  }
}

// The `landfall-questions` event subscription is created by the postdeploy hook
// (scripts/eventgrid.*): its webhook URL needs the function app's `blobs_extension`
// system key, which only exists after `azd deploy` has published the `start` function.

// ==================================================================
// Role assignments (data plane)
// ==================================================================
// --- workload identity (uami) -> storage
resource ra_uami_blob 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, uami.id, roles.storageBlobDataOwner)
  scope: storage
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.storageBlobDataOwner)
    principalId: uami.properties.principalId
    principalType: 'ServicePrincipal'
  }
}
resource ra_uami_queue 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, uami.id, roles.storageQueueDataContributor)
  scope: storage
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.storageQueueDataContributor)
    principalId: uami.properties.principalId
    principalType: 'ServicePrincipal'
  }
}
resource ra_uami_table 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, uami.id, roles.storageTableDataContributor)
  scope: storage
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.storageTableDataContributor)
    principalId: uami.properties.principalId
    principalType: 'ServicePrincipal'
  }
}
// --- uami -> search (data + service, to let postprovision build the index)
resource ra_uami_searchData 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(search.id, uami.id, roles.searchIndexDataContributor)
  scope: search
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.searchIndexDataContributor)
    principalId: uami.properties.principalId
    principalType: 'ServicePrincipal'
  }
}
resource ra_uami_searchSvc 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(search.id, uami.id, roles.searchServiceContributor)
  scope: search
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.searchServiceContributor)
    principalId: uami.properties.principalId
    principalType: 'ServicePrincipal'
  }
}
// --- uami -> Foundry (agent runtime + model calls)
resource ra_uami_aiDev 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(foundry.id, uami.id, roles.azureAiDeveloper)
  scope: foundry
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.azureAiDeveloper)
    principalId: uami.properties.principalId
    principalType: 'ServicePrincipal'
  }
}
resource ra_uami_openai 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(foundry.id, uami.id, roles.cognitiveServicesOpenAiUser)
  scope: foundry
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.cognitiveServicesOpenAiUser)
    principalId: uami.properties.principalId
    principalType: 'ServicePrincipal'
  }
}
resource ra_uami_foundryUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(foundry.id, uami.id, roles.foundryUser)
  scope: foundry
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.foundryUser)
    principalId: uami.properties.principalId
    principalType: 'ServicePrincipal'
  }
}
// --- uami -> ACR + Key Vault
resource ra_uami_acr 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, uami.id, roles.acrPull)
  scope: acr
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.acrPull)
    principalId: uami.properties.principalId
    principalType: 'ServicePrincipal'
  }
}
resource ra_uami_kv 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, uami.id, roles.keyVaultSecretsUser)
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.keyVaultSecretsUser)
    principalId: uami.properties.principalId
    principalType: 'ServicePrincipal'
  }
}
// --- Search system identity -> read blobs + call embeddings (integrated vectorization)
resource ra_search_blob 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, search.id, roles.storageBlobDataReader)
  scope: storage
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.storageBlobDataReader)
    principalId: search.identity.principalId
    principalType: 'ServicePrincipal'
  }
}
resource ra_search_openai 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(foundry.id, search.id, roles.cognitiveServicesOpenAiUser)
  scope: foundry
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.cognitiveServicesOpenAiUser)
    principalId: search.identity.principalId
    principalType: 'ServicePrincipal'
  }
}
// --- deploying user -> data planes (so postprovision scripts work)
resource ra_me_blob 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  name: guid(storage.id, principalId, roles.storageBlobDataOwner)
  scope: storage
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.storageBlobDataOwner)
    principalId: principalId
    principalType: 'User'
  }
}
resource ra_me_search 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  name: guid(search.id, principalId, roles.searchIndexDataContributor)
  scope: search
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.searchIndexDataContributor)
    principalId: principalId
    principalType: 'User'
  }
}
resource ra_me_ai 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  name: guid(foundry.id, principalId, roles.azureAiDeveloper)
  scope: foundry
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.azureAiDeveloper)
    principalId: principalId
    principalType: 'User'
  }
}

// ==================================================================
// outputs
// ==================================================================
output storageAccountName string = storage.name
output storageBlobEndpoint string = storage.properties.primaryEndpoints.blob
output searchEndpoint string = 'https://${search.name}.search.windows.net'
output openAiEndpoint string = foundry.properties.endpoint
output foundryAccountName string = foundry.name
output foundryProjectEndpoint string = '${foundry.properties.endpoint}api/projects/landfall'
output sqlServerFqdn string = sqlServer.properties.fullyQualifiedDomainName
output sqlDatabaseName string = sqlDatabase.name
output functionAppName string = functionApp.name
output eventGridSystemTopicName string = egSystemTopic.name
output containerAppName string = containerApp.name
output containerAppUri string = 'https://${containerApp.properties.configuration.ingress.fqdn}'
output containerRegistryLoginServer string = acr.properties.loginServer
output uamiClientId string = uami.properties.clientId
output uamiPrincipalId string = uami.properties.principalId
output uamiName string = uami.name
