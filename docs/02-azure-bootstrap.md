# Azure bootstrap and registry foundation

This is the next hands-on checkpoint after successful local Compose and GHCR
publication. Azure resources have NOT been applied by the assistant. The supplied
subscription and tenant IDs are identifiers, not passwords. Execute the commands
from your own authenticated terminal. No credentials should be pasted into chat.

## Decisions and scope

| Decision | Reason |
| --- | --- |
| One ACR, no ongoing GHCR mirror | Azure-only deployment and native kubelet identity; avoids maintaining two release registries |
| Separate bootstrap and registry roots/state | Registry changes cannot tear down state storage |
| Four private state containers | Future nonprod/prod identities receive container-scoped state access |
| Separate infrastructure, publisher and diagnostic identities | Publishing an image does not permit changing infrastructure or reading state |
| Environment-scoped GitHub federation | Exact repository/environment subject, paired with main-only deployment rules |
| ACR Basic + Entra ABAC repository permissions | Lab-sized image storage; publisher limited to the two named repositories |
| State firewall permits one operator IPv4 | Bootstrap state is not accessible from arbitrary GitHub-hosted runner IPs |
| Storage LRS, platform encryption | Explicit lab choice; no zone/region disaster-recovery guarantee and no customer-managed encryption key requirement |

Basic ACR uses an authenticated public endpoint. It is **not network-private**.
Private ACR requires Premium, private DNS and a connected private runner. State
storage temporarily uses a public endpoint restricted to the operator IP; it
will move behind private networking when that runner exists. OIDC supplies
identity, not network connectivity. We do not allow all Azure/GitHub IPs.

The bootstrap creates two resource groups, one state account, four state
containers, a history lifecycle rule, a deletion lock, three user-assigned
identities, their federation rules and scoped IAM grants. It creates no AKS,
database, Front Door or monitoring resources. The registry root subsequently
creates just one Basic ACR. Its image data permissions are granted by a separate
operator bootstrap update; ordinary infrastructure CI has no IAM administration.

## 1. Apply this patch through a pull request

From the repository root, with a clean working tree:

```bash
git switch main
git pull --ff-only
git switch -c infra/azure-bootstrap
git apply --check /path/to/azure-bootstrap.patch
git apply /path/to/azure-bootstrap.patch
git add .github/workflows/ci.yml .github/workflows/azure-oidc-check.yml .github/workflows/terraform-check.yml .gitignore infra scripts/configure_azure_backend.py docs README.md
git commit -m "Add scoped Azure bootstrap and ACR foundation"
git push -u origin infra/azure-bootstrap
```

Open a PR into main and wait for backend-test, frontend-test, container-check,
terraform-check (bootstrap) and terraform-check (registry).
Their job IDs remain unchanged. If your ruleset restricts checks by workflow
name, update it for `Test and build`; publication to GHCR is now paused. Historical
At this bootstrap checkpoint GHCR publisher scripts remain historical; Step 3 replaces them. CI no longer invokes
publication or has packages:write. Do not run them to publish future releases.
The new Terraform workflow installs locked providers with backend=false and
validates both roots without Azure credentials. After these checks appear, add
both Terraform checks to your main ruleset. The OIDC check workflow is manual and
requires successful bootstrap first.

## 2. Install and verify tools, select the account

On macOS, install Azure CLI through Homebrew and Terraform through HashiCorp's
tap. Use Terraform **1.16.5**, as pinned in infra/.terraform-version; if your
installation differs, install that exact release before running the commands.
AzureRM **5.8.0** and multi-platform checksums are pinned in the committed lock
files. A version upgrade is a reviewed PR, not an unannounced pipeline change.

```bash
brew install azure-cli
brew tap hashicorp/tap
brew install hashicorp/tap/terraform
az version
terraform version
az login --tenant 133815cf-acdc-4089-a1e7-fce0de2fe1b4
az account set --subscription b4207b90-6a00-470a-aa95-b154c688bb74
az account show --query '{name:name,id:id,tenantId:tenantId,state:state}' --output json
az ad signed-in-user show --query id --output tsv
```

Verify the exact tenant/subscription and Enabled subscription status. Save the
last command's value as operator_object_id. This runbook bootstraps with an
interactive user, not a service principal. If directory lookup is unavailable,
obtain your user object ID from Entra ID > Users in the portal.

In Subscription > Access control (IAM) > View my access, verify active resource
creation AND role-assignment permissions. Owner is sufficient; Contributor
alone is not. In a company this is a designated, controlled bootstrap operator,
often with temporary privileged access. These rights are never assigned to the
image publisher. Activate any required PIM access before continuing.

Register these providers once using the bootstrap operator:

```bash
for provider in Microsoft.Storage Microsoft.ManagedIdentity Microsoft.ContainerRegistry; do
  az provider register --namespace "$provider" --wait
done
```

The provider is configured not to perform broad automatic registrations.
Check Central India availability, your subscription's Azure Policy restrictions
and the Storage/ACR estimate in Azure Pricing Calculator before applying. Create
a cost budget in the subscription's billing currency; no currency or budget
amount is assumed in this patch. Budget alerts do not cap expenditure.

## 3. Configure and plan the bootstrap

```bash
cp infra/bootstrap/terraform.tfvars.example infra/bootstrap/terraform.tfvars
```

Edit operator_object_id and operator_public_ipv4 in the copied file. Obtain your
current public IPv4 through your network administrator/router or, optionally:

```bash
curl -4 https://api.ipify.org
```

Keep registry_resource_id unset for the first apply. Use the subscription/tenant
values already supplied. The copied tfvars file is ignored; the example is safe
to commit. Do not change the prefix after resources exist: it determines names.

Set a private default permission for locally generated plans/state, and use
interactive Azure CLI authentication:

```bash
umask 077
export ARM_USE_CLI=true
export ARM_USE_AZUREAD=true
export ARM_USE_OIDC=false
terraform -chdir=infra/bootstrap init -input=false -lockfile=readonly
terraform -chdir=infra/bootstrap fmt -check
terraform -chdir=infra/bootstrap validate
terraform -chdir=infra/bootstrap plan -out=bootstrap.tfplan
```

This initial root deliberately has no remote backend yet. Review the resource
groups, storage firewall, IAM scopes and federation subjects in the plan. The
publisher has **no permissions yet**: its ACR-specific grants cannot exist before
the registry. No secret values are being created.

Apply the exact reviewed plan:

```bash
terraform -chdir=infra/bootstrap apply bootstrap.tfplan
```

If any apply fails, retain the local state and rerun plan after fixing the cause;
do not restart from an empty directory or recreate the resources in the portal.

## 4. Migrate bootstrap state into Azure

The newly created operator blob grants can take time to propagate. Verify data
access before migration. Obtain the account name without dumping full state:

```bash
terraform -chdir=infra/bootstrap output -json configuration
```

Using storage_account_name from that output:

```bash
az storage container show --account-name ACTUAL_STATE_ACCOUNT --name tfstate-bootstrap --auth-mode login --query name --output tsv
```

Replace ACTUAL_STATE_ACCOUNT. A 403 can mean either IAM propagation or the IP
firewall; diagnose before changing anything. Never enable Shared Key or broad
network bypass to work around it.

Generate ignored, nonsecret backend files, then migrate:

```bash
terraform -chdir=infra/bootstrap output -json configuration | python3 scripts/configure_azure_backend.py
terraform -chdir=infra/bootstrap init -migrate-state -backend-config=../.generated/bootstrap.backend.hcl
```

Terraform asks whether to copy the existing state to the remote backend. Answer
yes after verifying the destination. Do **not** use -reconfigure here: that does
not migrate the initial local state. The generated backend.local.tf deliberately
remains ignored until bootstrap resources exist.

Verify the remote blob and a converged plan:

```bash
az storage blob show --account-name ACTUAL_STATE_ACCOUNT --container-name tfstate-bootstrap --name terraform.tfstate --auth-mode login --query '{name:name,bytes:properties.contentLength}' --output json
terraform -chdir=infra/bootstrap plan -detailed-exitcode
```

Expected: a nonempty remote state blob and exit code 0 / No changes. Terraform
automatically leases the remote blob while modifying state. In a later drill we
will prove concurrent operations are refused; never disable locking to bypass
contention. List available previous versions via the portal without modifying
state. Do not upload state, saved plans or terraform show -json to GitHub.

Only after verification, remove the generated local bootstrap.tfplan and stale
local terraform.tfstate/terraform.tfstate.backup copies. Preserve the ignored
backend configuration and tfvars needed for subsequent bootstrap maintenance.

## 5. Create ACR using its separate remote state

Run from the same operator terminal after successful migration:

```bash
terraform -chdir=infra/registry init -input=false -lockfile=readonly -backend-config=../.generated/registry.backend.hcl
terraform -chdir=infra/registry validate
terraform -chdir=infra/registry plan -var-file=../.generated/registry.auto.tfvars.json -out=registry.tfplan
terraform -chdir=infra/registry apply registry.tfplan
terraform -chdir=infra/registry output -json registry
```

Review the plan before executing apply. It must create exactly the intended Basic
registry, with admin_enabled=false and AbacRepositoryPermissions. No new resource
group is needed: bootstrap owns the existing registry group. The first registry
apply is deliberately operator-driven. Its later CI identity has the built-in
Container Registry Contributor and Data Access Configuration Administrator role
only on that resource group, and blob data access only to tfstate-registry. It
does not receive general resource-group Contributor or role-assignment rights.

Copy the registry id from the output into registry_resource_id in the ignored
bootstrap/terraform.tfvars. Grant its data access through a separate reviewed
bootstrap plan:

```bash
terraform -chdir=infra/bootstrap plan -out=registry-access.tfplan
terraform -chdir=infra/bootstrap apply registry-access.tfplan
```

Expected additions: publisher repository Writer, publisher registry Reader for
CLI discovery/login, and operator repository Reader. Image data permissions are
conditioned to the exact backend/frontend names, using the Request repository
attribute. No catalog-wide listing or image deletion is granted. Even an Owner
does not automatically get ABAC image data permissions. Azure must validate the
conditions at apply, and positive/negative push tests will verify them before CI
publication is enabled. IAM administration stays in operator-controlled bootstrap.

Check the deployed configuration, substituting the actual output names:

```bash
az acr show --name ACTUAL_REGISTRY_NAME --resource-group ACTUAL_REGISTRY_GROUP --query '{name:name,sku:sku.name,admin:adminUserEnabled,mode:roleAssignmentMode,publicNetwork:publicNetworkAccess}' --output json
```

Expected Basic, admin false, ABAC mode and public network Enabled. This registry
has an authenticated public endpoint, not a private endpoint. A future Premium
networking exercise will explicitly address its additional cost and runners.

## 6. Configure GitHub OIDC and run the harmless access check

In repository Settings > Environments, create these exact names:

| Environment | Identity | Use |
| --- | --- | --- |
| azure-oidc-check | check_reader | Read-only diagnostic workflow |
| infra-registry | registry_infra | Future controlled Terraform workflow |
| acr-publish | publisher | Future main-only image publication |

For each environment, set deployment branches/tags to selected branches and allow
only main. Federation uses the environment subject: **Azure cannot independently
see the branch in that subject**. GitHub's branch restrictions are therefore
required. Configure review requirements appropriate for your solo lab; requiring
a different reviewer when no other person exists will block it. Nonprod/prod
deployment environments and identities come with their infrastructure phase.

Run the backend configuration helper again if you need the nonsecret IDs. In
Settings > Secrets and variables > Actions > Variables, set:

- AZURE_SUBSCRIPTION_ID
- AZURE_TENANT_ID
- AZURE_CHECK_READER_CLIENT_ID
- AZURE_BOOTSTRAP_RESOURCE_GROUP
- AZURE_REGISTRY_RESOURCE_GROUP

The helper prints exact values. Keep registry_infra/publisher client IDs available
for the later workflows. Do not create AZURE_CLIENT_SECRET, a storage-key secret,
or an ACR password. No Key Vault is needed to store nonexistent credentials.

After the PR is merged into main, Actions > Verify Azure OIDC scope > Run workflow
on main. Expected success: the registry resource group can be read; reading the
bootstrap resource group fails specifically with AuthorizationFailed. The job
does not access blobs, publish images, create/delete resources or emit telemetry.
Its dedicated reader has no state access and cannot publish an image.

## Troubleshooting and recovery

- AADSTS70021 / no matching federation: inspect exact repository case, environment
  name, subject, tenant and client ID. Do not replace OIDC with a client secret.
- RoleAssignment write denied: operator lacks active IAM administration, or a
  company policy disallows the grant. Contributor alone is insufficient.
- State firewall: if your public IPv4 changes, you cannot initialize the remote
  backend to change its own firewall. As the privileged operator, add the new IP
  through az storage account network-rule add (management plane), update tfvars,
  and apply the converging bootstrap plan. Remove the obsolete rule in Terraform.
- Self-hosted/private Terraform runners are not provisioned yet. Do not run a
  storage-backed Terraform job on a GitHub-hosted runner or loosen the firewall.
- A GitHub check run cannot prove publisher authorization. Later positive pushes,
  negative unrelated-repository pushes and reader push denials must pass separately.
- Azure CanNotDelete protects the account's control plane, not arbitrary blob
  deletes. Versioning, soft deletion and data-plane IAM protect state contents.
- Cleanup: retain remote state while dismantling workload/registry resources.
  Bootstrap is last. Deliberately remove the Azure lock and prevent_destroy guards
  through reviewed maintenance; do not run an unqualified terraform destroy.
  Deletion protection is a guard, not an absolute guarantee against an administrator.

## What remains after this checkpoint

Before cloud deployment: implement and verify dependency/image/source security
gates, base-image digest/agent checksum pinning, ACR main-only publication, paired
digest release manifests, signatures/provenance policy, scoped kubelet Reader
roles, private runners/state networking and protected plan/apply workflows. Saved
plans will use access-controlled Azure storage, not public GitHub artifacts.
AKS/DB/Front Door/Helm/Key Vault/telemetry/alerts/DNS remain later checkpoints.
No GitHub Actions build metrics are sent to Azure.

Sources:
- https://developer.hashicorp.com/terraform/language/backend/azurerm
- https://learn.microsoft.com/azure/storage/blobs/data-protection-overview
- https://learn.microsoft.com/azure/container-registry/container-registry-skus
- https://learn.microsoft.com/azure/container-registry/container-registry-rbac-abac-repository-permissions
- https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-azure

After the registry/federation checks pass, continue with [Step 3: secure ACR CI](03-secure-acr-ci.md). Step 3 does not change these Terraform resources or federation subjects.
