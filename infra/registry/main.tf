terraform {
  required_version = "= 1.16.5"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "= 5.8.0"
    }
  }
  backend "azurerm" {}
}

provider "azurerm" {
  features {}
  subscription_id                 = var.subscription_id
  tenant_id                       = var.tenant_id
  resource_provider_registrations = "none"
}

variable "subscription_id" { type = string }
variable "tenant_id" { type = string }
variable "location" { type = string }
variable "registry_resource_group" { type = string }
variable "registry_name" { type = string }

module "registry" {
  source              = "../modules/registry"
  name                = var.registry_name
  resource_group_name = var.registry_resource_group
  location            = var.location
  tags = {
    project     = "ci-cd-project"
    environment = "shared"
    owner       = "anuragdchowdhury"
    managed_by  = "terraform"
    purpose     = "application-images"
  }
}

output "registry" {
  value = {
    id           = module.registry.id
    name         = module.registry.name
    login_server = module.registry.login_server
  }
}
