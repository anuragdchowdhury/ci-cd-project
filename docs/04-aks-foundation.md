# 04 — Provision the AKS and database foundation

This checkpoint creates Azure resources, not a running website. Deploy Dev only through the existing `nonprod` root. Staging is removed from the active configuration, and the unprovisioned prod root is removed. Existing bootstrap, registry and remote-state resources are unchanged. Terraform runs from your authenticated laptop for this checkpoint. Cloud APIs are reachable from your laptop; private AKS, database and Key Vault data endpoints are not. The next checkpoint supplies private runner/operator access, namespace bootstrap, SQL grants and Helm. We do not temporarily expose those services to make a test pass.

## What this PR creates and why

| Component | Dev configuration | Purpose |
|---|---|---|
| Resource group / VNet | `rg-nk-nonprod`, `10.20.0.0/16` | Keep the existing nonprod naming/state key; Dev is its only environment |
| Private AKS | `aks-notekeeper-nonprod` | One cluster; no staging/prod cluster |
| System pool | Two fixed `Standard_D4s_v4` nodes, autoscaling off, zones unset | Eight Compute vCPUs within the recorded ten-vCPU regional/family quota |
| PostgreSQL 16 | B1ms, 32 GiB, only `notekeeper_dev` | Private networking, Entra-only authentication, seven-day backups; HA off |
| Key Vault | Dev only | Private endpoint, RBAC, seven-day soft delete/purge protection |
| Runtime/migration identities | Dev only, separate per purpose | AKS federation; runtime reads its vault; SQL grants come next |
| Deploy identity | Dev namespace RBAC | GitHub `dev` environment OIDC, no cloud secret |
| Kubelet identity | Two-repository ACR Reader | Passwordless image pulls; no imagePullSecrets |
| Private state endpoint | Blob endpoint/DNS in the Dev VNet | Future private runner connectivity without opening the storage firewall |
| Reserved subnets | Runner and ingress/Private Link | Subsequent deployment and Front Door work |
| Budget alerts | Platform and AKS node groups separately | Email thresholds, not one combined budget or spend cap |

Pods use Azure CNI Overlay + Cilium. Egress uses an AKS-managed standard load balancer; private API does not mean no outbound Internet. AKS creates/owns its node resource group, disks, API private DNS and load-balancer components. Terraform owns our cluster/network declaration; do not manually change AKS-managed resources.

There is no Front Door, Grafana, DCR, telemetry collection, application deployment, SQL principal registration or deployment runner yet. These remain the following milestones. Dev SQL runtime/migration privilege separation must be validated after grants; database creation alone is not sufficient. Managed Prometheus, Managed Grafana, DCR/Log Analytics container logs and OTel traces with a configured backend are still required. Front Door Premium and managed observability do not consume the Compute vCPU quota; their in-cluster agents share the fixed node resources.

## 1. Merge after checks pass

Merge the Dev quota revision PR after its three Terraform checks pass. PR #10 is already merged. Then:

```bash
git switch main
git pull --ff-only
az account set --subscription b4207b90-6a00-470a-aa95-b154c688bb74
az account show --query '{subscription:id,tenant:tenantId,state:state}' -o table
```

Keep using the operator account with Owner access for these initial resource/role assignments. The eventual application deploy identities have namespace scope; they cannot create infrastructure or grant IAM.

## 2. Reconcile the catalog role you added in the portal

If this role is already imported, skip the import and check the bootstrap plan. Otherwise import the existing assignment instead of creating a duplicate. Your original ignored bootstrap variables and backend must still be present. Do not run init -migrate-state again merely because this PR adds roots.

```bash
CATALOG_ROLE_ID=$(az role assignment list \
  --assignee "$(az ad signed-in-user show --query id -o tsv)" \
  --scope /subscriptions/b4207b90-6a00-470a-aa95-b154c688bb74/resourceGroups/rg-nk-registry-ci/providers/Microsoft.ContainerRegistry/registries/acrnk81c108fc \
  --query "[?roleDefinitionName=='Container Registry Repository Catalog Lister'].id | [0]" -o tsv)
```

If this is empty, confirm you assigned the role to the same account used by Azure CLI. If it contains a role-assignment resource ID:

```bash
terraform -chdir=infra/bootstrap import \
  'azurerm_role_assignment.operator_catalog_lister["registry"]' "$CATALOG_ROLE_ID"
terraform -chdir=infra/bootstrap plan
```

Expect no changes to the existing bootstrap resources after import. If Terraform reports another unexpected change, resolve it before applying; do not blindly approve it. No bootstrap apply is needed for an assignment already imported successfully.

## 3. Register providers and check capacity

```bash
for provider in Microsoft.Compute Microsoft.Network Microsoft.ContainerService Microsoft.DBforPostgreSQL Microsoft.KeyVault Microsoft.ManagedIdentity Microsoft.Consumption; do
  az provider register --namespace "$provider"
done
az provider list --query "[?namespace=='Microsoft.Compute' || namespace=='Microsoft.Network' || namespace=='Microsoft.ContainerService' || namespace=='Microsoft.DBforPostgreSQL' || namespace=='Microsoft.KeyVault' || namespace=='Microsoft.ManagedIdentity' || namespace=='Microsoft.Consumption'].{provider:namespace,state:registrationState}" -o table
az aks get-versions --location centralindia -o table
az vm list-skus --location centralindia --size Standard_D4s_v4 --all \
  --query "[?name=='Standard_D4s_v4'].{name:name,restrictions:restrictions}" -o json
az vm list-usage --location centralindia -o table
az postgres flexible-server list-skus --location centralindia -o table
```

Wait until registrations show Registered. Choose an available GA AKS patch version from the output; record the exact version rather than selecting a preview or guessing. D4s_v4 must not have a region-wide restriction. The recorded restriction is zone 1 only; this pool leaves `zones` unset. Recheck the actual returned restriction type and region, rather than treating a zone restriction as a ban on the entire SKU. Confirm B1ms is available. SKU discovery does not guarantee regional capacity at apply time.

The recorded regional quota is ten vCPUs, DSv5 quota is zero, and DSv4 quota is ten. Two D4s_v4 nodes consume eight vCPUs, leaving at most two regional vCPUs for a future runner VM or other Compute resources. Check current usage as well as limits. No autoscaler or extra user pool is enabled. Regional capacity is established only when Azure successfully provisions the nodes.

**Upgrade limitation:** this two-node system pool cannot use the requested no-extra-VM rolling upgrade under the pinned provider/service constraints. AzureRM 5.8.0 exposes `max_surge` for the default pool but not `max_unavailable`; Microsoft states that max unavailable cannot be set on system node pools. Setting `max_surge = "0"` alone is not a supported workaround. We retain the supported surge value `"1"`, disable automatic Kubernetes upgrades (channel omitted/null) and automatic node OS image upgrades (`None`), and do not schedule an upgrade within the current quota.

A normal surge upgrade would temporarily need three D4s_v4 nodes: twelve vCPUs, beyond the current ten-vCPU limit. Obtain enough regional and DSv4 quota for the surge plus any runner/other VMs before upgrading, or review a different supported maintenance architecture. Disabling upgrades is a temporary lab tradeoff, not a long-term patch strategy. Do not assume VM-size rotation, node-image upgrades or changing the selected Kubernetes version can proceed at eight vCPUs. A manual `kubectl drain` exercise is different from a managed node upgrade and does not prove upgrade support. During any drain, check PDBs and that the remaining node can fit the application and telemetry agents; availability may decrease.

Before apply, use https://azure.microsoft.com/pricing/calculator/ to estimate Central India D4s_v4 Linux nodes (two fixed; upgrades are deferred until quota is resolved), PostgreSQL B1ms + 32 GiB storage, private endpoints, load balancer/disks and networking. Check the subscription's billing currency. Later include Front Door Premium, Grafana, telemetry and private runners; they are not covered by this checkpoint's estimate. Budget alerts notify, never shut resources down. Do not treat the budget amount below as an estimated bill.

## 4. Generate ignored configuration

The existing generator writes the Dev nonprod backend file, plus the existing bootstrap/registry files, pointing to your already-created containers. This command does not migrate or modify remote state:

```bash
terraform -chdir=infra/bootstrap output -json configuration | python3 scripts/configure_azure_backend.py
```

Replace the three values below. The budget is an alert threshold in your subscription's billing currency, separately for each resource group. Use an email you control. The script checks the Azure CLI subscription/tenant and records your signed-in Entra user as the DB administrator.

```bash
terraform -chdir=infra/bootstrap output -json configuration | \
  python3 scripts/configure_platform.py \
    --kubernetes-version 'REPLACE_WITH_SUPPORTED_GA_PATCH' \
    --budget-amount REPLACE_WITH_POSITIVE_NUMBER \
    --alert-email 'REPLACE_WITH_YOUR_EMAIL'
```

Regenerate the inputs even if you generated them before this revision: the old file can still contain D4s_v5. Delete/discard any unapplied saved nonprod plan from the old configuration; make a new plan below. Review `infra/.generated/nonprod.auto.tfvars.json`. It contains identifiers/configuration, not credentials, and is ignored by Git. Do not publish plans or full state. Keep your existing operator IPv4 storage firewall rule current if your public IP changed.

## 5. Plan, review and apply nonprod

```bash
terraform -chdir=infra/nonprod init -input=false \
  -backend-config=../.generated/nonprod.backend.hcl
terraform -chdir=infra/nonprod validate
terraform -chdir=infra/nonprod plan \
  -var-file=../.generated/nonprod.auto.tfvars.json \
  -out=nonprod.tfplan
terraform -chdir=infra/nonprod show -no-color nonprod.tfplan
```

Before planning, confirm whether any nonprod resources were created by a previous failed apply: the remote state is the authority. Do not reset/delete it. For an empty nonprod state, the plan should only add the Dev foundation; it should create no staging or prod resources. If resources already exist, inspect any replacement/destruction, especially the node SKU and removed staging resources, before applying. It must not destroy/replace your bootstrap storage or registry: this root owns neither. Review `Standard_D4s_v4`, `node_count = 2`, autoscaling false, zones unset, automatic node upgrades disabled, only Dev identities/database/vault, the private API, Entra-only PostgreSQL and scoped image/deploy permissions. The supported one-node surge value remains an upgrade limitation; it does not allocate an extra VM at initial creation.

Then apply the exact reviewed plan (this starts billable Azure resources):

```bash
terraform -chdir=infra/nonprod apply nonprod.tfplan
terraform -chdir=infra/nonprod output -json platform
terraform -chdir=infra/nonprod plan \
  -var-file=../.generated/nonprod.auto.tfvars.json
```

Expect No changes on the follow-up plan. Creation can take tens of minutes. If a capacity, quota or permissions error occurs, retain the remote state; diagnose and re-plan after fixing it. Do not delete state or repeatedly create a new stack.

## 6. Validate the Azure foundation

```bash
az aks show -g rg-nk-nonprod -n aks-notekeeper-nonprod \
  --query '{state:provisioningState,privateAPI:apiServerAccessProfile.enablePrivateCluster,localAccountsDisabled:disableLocalAccounts,upgradeChannels:autoUpgradeProfile,oidc:oidcIssuerProfile.enabled,workloadIdentity:securityProfile.workloadIdentity.enabled,pools:agentPoolProfiles[].{name:name,size:vmSize,count:count,autoscaling:enableAutoScaling,zones:availabilityZones,upgradeSettings:upgradeSettings}}' -o json
az postgres flexible-server list -g rg-nk-nonprod \
  --query '[].{name:name,state:state,publicAccess:network.publicNetworkAccess,authentication:authConfig}' -o json
az keyvault list -g rg-nk-nonprod --query '[].{name:name,publicAccess:properties.publicNetworkAccess,rbac:properties.enableRbacAuthorization}' -o json
az network private-endpoint list -g rg-nk-nonprod \
  --query '[].{name:name,state:provisioningState,connections:privateLinkServiceConnections[].privateLinkServiceConnectionState.status}' -o json
```

Look for exactly two D4s_v4 nodes, autoscaling false, no configured availability zones, only Dev database/vault/identities, node OS upgrades None, and succeeded/ready resources, private AKS enabled, workload identity enabled, local accounts disabled, PostgreSQL public access disabled/password auth disabled, and Approved private endpoint connections.

This proves Azure provisioning, not end-to-end connectivity. `kubectl` from your laptop and reading Key Vault secrets should not work without private network access. At the next checkpoint, we verify DNS resolves privately from the runner, image pulls succeed, register DB principals, apply namespace permissions and deploy dev.

Share the **nonsecret output of `terraform output -json platform`**, the Azure checks above and the follow-up plan summary. Do not send state, plans, access tokens or kubeconfig.

## Deferred environments and shutdown

Staging/prod roots and provisioning are not part of this active lab. The original bootstrap state containers (including `tfstate-prod`) remain intact; do not delete them. Stale ignored prod input/backend files may remain on your laptop, but this revision neither generates nor applies prod. The cluster/root keep their nonprod names to avoid needless state/address renaming.

For a pause, stopping AKS and PostgreSQL saves some compute charges but storage, private endpoints and networking continue billing. For permanent cleanup later, remove Helm/Front Door/runner dependencies first, then use `terraform destroy -var-file=../.generated/nonprod.auto.tfvars.json` in this root. Review the destroy plan. Key Vault purge protection means deleted vault names cannot immediately be reused; recover the vault or wait for retention. Never destroy the bootstrap state storage as part of this cleanup.

## References

- System pools and minimum VM sizing: https://learn.microsoft.com/azure/aks/use-system-pools
- Workload identity: https://learn.microsoft.com/azure/aks/workload-identity-deploy-cluster
- PostgreSQL private networking: https://learn.microsoft.com/azure/postgresql/network/concepts-networking-private
- ACR ABAC permissions: https://learn.microsoft.com/azure/container-registry/container-registry-rbac-abac-repository-permissions

- AKS rolling-upgrade constraints: https://learn.microsoft.com/azure/aks/upgrade-aks-node-pools-rolling
- Pinned default-pool provider schema: https://github.com/hashicorp/terraform-provider-azurerm/blob/v5.8.0/website/docs/r/kubernetes_cluster.html.markdown
