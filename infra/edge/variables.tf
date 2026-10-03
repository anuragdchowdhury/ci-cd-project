variable "subscription_id" { type = string }
variable "tenant_id" { type = string }
variable "location" {
  type    = string
  default = "centralindia"
}
variable "resource_group" { type = string }
variable "ingress_subnet_id" { type = string }
variable "load_balancer_frontend_id" { type = string }
variable "dev_dns_zone" { type = string }
variable "law_id" { type = string }
variable "action_group_id" { type = string }

variable "operator_ipv4" { type = string }
