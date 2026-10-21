param location string = resourceGroup().location

resource plan 'Microsoft.Web/serverfarms@2023-01-01' = {
  name: 'taskboard-plan'
  location: location
}

resource web 'Microsoft.Web/sites@2023-01-01' = {
  name: 'taskboard-web'
  location: location
  kind: 'app,linux,container'
}

resource worker 'Microsoft.Web/sites@2023-01-01' = {
  name: 'taskboard-worker'
  location: location
  kind: 'functionapp,linux'
}

resource pg 'Microsoft.DBforPostgreSQL/flexibleServers@2023-06-01-preview' = {
  name: 'taskboard-pg'
  location: location
}

resource storage 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: 'taskboardfiles'
  location: location
  kind: 'StorageV2'
}

resource vault 'Microsoft.KeyVault/vaults@2023-02-01' = {
  name: 'taskboard-kv'
  location: location
}

resource redis 'Microsoft.Cache/redis@2023-08-01' = {
  name: 'taskboard-cache'
  location: location
}

resource bus 'Microsoft.ServiceBus/namespaces@2022-10-01-preview' = {
  name: 'taskboard-bus'
  location: location
}

resource insights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'taskboard-ai'
  location: location
  kind: 'web'
}

resource shared 'Microsoft.Network/virtualNetworks@2023-05-01' existing = {
  name: 'hub-vnet'
}
