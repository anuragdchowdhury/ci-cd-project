terraform {
  required_version = "= 1.16.5"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "= 5.8.0"
    }
  }
}

# Backend configuration is generated only AFTER the initial local bootstrap.
# Never enable a remote backend pointing at storage which does not exist yet.
provider "azurerm" {
  features {}
  subscription_id                 = var.subscription_id
  tenant_id                       = var.tenant_id
  storage_use_azuread             = true
  resource_provider_registrations = "none"
}
