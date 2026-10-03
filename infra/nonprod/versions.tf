terraform {
  required_version = "= 1.16.5"
  required_providers {
    azurerm = { source = "hashicorp/azurerm", version = "= 5.8.0" }
  }
  backend "azurerm" {}
}
provider "azurerm" {
  features {}
  subscription_id                 = var.subscription_id
  tenant_id                       = var.tenant_id
  resource_provider_registrations = "none"
}
