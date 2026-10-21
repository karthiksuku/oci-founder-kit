resource "azurerm_container_app" "api" {
  name = "taskboard-api"
}

resource "azurerm_cosmosdb_account" "docs" {
  name = "taskboard-docs"
  kind = "MongoDB"
}

resource "azurerm_storage_account" "files" {
  name = "taskboardfiles"
}
