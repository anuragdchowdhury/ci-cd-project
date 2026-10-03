terraform {
  required_providers {
    azurerm = { source = "hashicorp/azurerm" }
  }
}

variable "name" { type = string }
variable "resource_group_name" { type = string }
variable "location" { type = string }
variable "tags" { type = map(string) }

resource "azurerm_container_registry" "this" {
  name                          = var.name
  resource_group_name           = var.resource_group_name
  location                      = var.location
  sku                           = "Basic"
  admin_enabled                 = false
  public_network_access_enabled = true
  role_assignment_mode          = "AbacRepositoryPermissions"
  tags                          = var.tags
  # Basic does not support enabling anonymous pulls or private endpoints.
  # Do not add unsupported Premium-only diagnostic/retention settings here.
  lifecycle { prevent_destroy = true }
}

output "id" { value = azurerm_container_registry.this.id }
output "name" { value = azurerm_container_registry.this.name }
output "login_server" { value = azurerm_container_registry.this.login_server }
