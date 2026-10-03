variable "subscription_id" {
  type        = string
  description = "Subscription to bootstrap; supplied in the example configuration."
}

variable "tenant_id" {
  type = string
}

variable "location" {
  type    = string
  default = "centralindia"
}

variable "name_prefix" {
  type    = string
  default = "nk"
  validation {
    condition     = can(regex("^[a-z][a-z0-9]{1,7}$", var.name_prefix))
    error_message = "Use 2-8 lowercase alphanumeric characters, beginning with a letter."
  }
}

variable "github_repository" {
  type    = string
  default = "anuragdchowdhury/ci-cd-project"
  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.github_repository))
    error_message = "Use the exact GitHub owner/repository name."
  }
}

variable "operator_object_id" {
  type        = string
  description = "Object ID of the Azure user performing bootstrap. Keep this stable across operators."
  validation {
    condition     = can(regex("^[0-9a-fA-F-]{36}$", var.operator_object_id))
    error_message = "Supply the operator's Entra object ID, not their email or a client ID."
  }
}

variable "operator_public_ipv4" {
  type        = string
  description = "Your current public IPv4 address; limits access to the state storage endpoint."
  validation {
    condition     = can(cidrnetmask("${var.operator_public_ipv4}/32"))
    error_message = "Supply one public IPv4 address, without /32."
  }
}

variable "registry_resource_id" {
  type        = string
  default     = null
  description = "Set only after registry creation to grant repository-scoped publisher/operator access."
  validation {
    condition = var.registry_resource_id == null ? true : (startswith(lower(var.registry_resource_id), lower("/subscriptions/${var.subscription_id}/resourceGroups/rg-${var.name_prefix}-registry-ci/")) && can(regex(
      "(?i)^/subscriptions/[0-9a-f-]{36}/resourceGroups/[^/]+/providers/Microsoft.ContainerRegistry/registries/[a-z0-9]+$",
      var.registry_resource_id
    )))
    error_message = "Supply an ACR resource ID in this subscription's designated registry group, or leave null before ACR exists."
  }
}
