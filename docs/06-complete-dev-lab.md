# Step 6 — finish the Dev lab in one session

This PR supplies the remaining deployment, edge, telemetry and scenario code. Terraform provisions Azure; Helm installs controllers/application releases; GitHub CD uses the deployment VM. DNS delegation and approval of Front Door's private endpoint are explicit operator actions. These dependencies require ordered operations, rather than a single blind apply. No staging/prod, extra nodes, autoscaler or GitHub build metrics are added.

## 1. Merge and prepare

After this PR's checks pass, merge it. On your laptop:

```bash
git switch main
git pull --ff-only
az account set --subscription b4207b90-6a00-470a-aa95-b154c688bb74
terraform -chdir=infra/bootstrap output -json configuration |
  python3 scripts/configure_azure_backend.py
```

This adds `edge.backend.hcl`: existing `tfstate-nonprod` container, separate `edge.tfstate` key. It does not migrate/delete existing state. Your current public IPv4 must still be allowed by the state-storage firewall and SSH NSG. If it changed, update bootstrap/access inputs and review their plans first. Keep all generated files/plans ignored; never commit state, tokens or private SSH keys.

Register providers if not already Registered:

```bash
for provider in Microsoft.Monitor Microsoft.Dashboard Microsoft.Insights Microsoft.OperationalInsights Microsoft.AlertsManagement Microsoft.Cdn; do
  az provider register --namespace "$provider" --wait
  az provider show --namespace "$provider" --query registrationState -o tsv
done
```

Wait for **Test and build** on the merged main commit to finish successfully. That commit's release contains the drill-capable backend; record its full SHA as `RELEASE_SHA`. CD will deploy its existing digest pair without rebuilding it.

## 2. Provision monitoring and Dev DNS

Use the agreed root domain **azuredevops.site** for this Dev lab. Azure DNS will host the whole domain. Before switching nameservers, inventory existing A/AAAA/CNAME/MX/TXT/CAA/SRV records at the current DNS host and recreate any records you need in Azure DNS. If DNSSEC is enabled, remove the old registrar DS record before the switch; do not leave a stale DS delegation. A restrictive CAA policy must permit the origin and Front Door certificate issuers. DNS migration can interrupt existing website/email services if their records are omitted.

```bash
DEV_ZONE=azuredevops.site
python3 scripts/configure_lab.py --dev-zone "$DEV_ZONE"
terraform -chdir=infra/nonprod init -backend-config=../.generated/nonprod.backend.hcl
terraform -chdir=infra/nonprod plan \
  -var-file=../.generated/nonprod.auto.tfvars.json \
  -var-file=../.generated/access.auto.tfvars.json \
  -var-file=../.generated/lab.auto.tfvars.json \
  -out=dev-lab.tfplan
terraform -chdir=infra/nonprod show -no-color dev-lab.tfplan
```

Review additions for monitoring, DNS, certificate identity/RBAC and alerts. The existing AKS adds its monitoring agents **in place**. Existing VM, database, vault, node size/count and bootstrap/registry must not be replaced/destroyed. Unexpected replacements mean stop and inspect the plan. Agents share the two existing nodes; check allocatable/requested resources after installation. Grafana/Monitor regional service availability and current Azure capacity are validated during provisioning, independently of Compute quota.

```bash
terraform -chdir=infra/nonprod apply dev-lab.tfplan
terraform -chdir=infra/nonprod output -json platform > infra/.generated/dev-platform.json
terraform -chdir=infra/nonprod output -json deployment_vm > infra/.generated/dev-vm.json
terraform -chdir=infra/nonprod output -json observability > infra/.generated/dev-observability.json
python3 -m json.tool infra/.generated/dev-observability.json
```

After preserving the existing records in Azure DNS, go to **Namecheap → Domain List → azuredevops.site → Manage → Nameservers → Custom DNS**. Enter **all four** actual `nameservers` from Terraform output and save. No Host field or `dev` NS record is needed for this root-domain migration. Wait for delegation/cache propagation before deploying certificates. Verify:

```bash
dig NS "$DEV_ZONE"
dig A "origin.$DEV_ZONE"
```

Expected: Azure authoritative nameservers and origin `10.20.19.10`. Publishing this private origin address does not expose the load balancer to the Internet. Cert-manager proves domain ownership with DNS-01; it does not require a publicly reachable origin. It receives only DNS Zone Contributor on this DNS zone using workload identity.

## 3. Finish existing SQL bootstrap and install controllers

The earlier **No changes** validates VM provisioning, not application deployment. Follow [Step 5 A](05-dev-deployment.md#a-merge-provision-the-access-vm-and-export-actual-configuration) for SSH host-key verification/tool checks if not already completed. Start the VM and obtain its current address:

```bash
az vm start -g rg-nk-nonprod -n vm-nk-dev-deploy
VM_IP=$(python3 -c 'import json; print(json.load(open("infra/.generated/dev-vm.json"))["public_ip"])')
RELEASE_SHA=PASTE_FULL_SUCCESSFUL_MAIN_COMMIT_SHA
GH_TOKEN="$(gh auth token)" python3 scripts/fetch_release.py "$RELEASE_SHA" \
  --registry acrnk81c108fc.azurecr.io --output infra/.generated/dev-release.json
python3 scripts/deployment_config.py \
  --platform infra/.generated/dev-platform.json --release infra/.generated/dev-release.json \
  --registry acrnk81c108fc.azurecr.io --observability infra/.generated/dev-observability.json \
  --output infra/.generated/dev-values.json
python3 scripts/configure_github_dev.py \
  --platform infra/.generated/dev-platform.json --vm infra/.generated/dev-vm.json \
  --registry acrnk81c108fc.azurecr.io
gh variable set DEV_OBSERVABILITY_JSON --repo anuragdchowdhury/ci-cd-project --env dev \
  < infra/.generated/dev-observability.json
scp -o StrictHostKeyChecking=yes -i "$HOME/.ssh/notekeeper-lab" \
  infra/.generated/dev-platform.json infra/.generated/dev-values.json infra/.generated/dev-observability.json \
  "labadmin@$VM_IP:"
ssh -o StrictHostKeyChecking=yes -i "$HOME/.ssh/notekeeper-lab" "labadmin@$VM_IP"
```

On the VM, clone the repository if needed, or fetch it; check out this reviewed main commit. Do not run CD concurrently with the operator session. Use temporary operator credentials because installing controllers/namespaces exceeds the Dev deployment identity's namespace rights:

```bash
cd ci-cd-project
git fetch origin main
git checkout --detach PASTE_FULL_MERGED_MAIN_COMMIT_SHA
(
  set -e
  export AZURE_CONFIG_DIR="$(mktemp -d)"
  export KUBECONFIG="$(mktemp)"
  trap 'rm -rf "$AZURE_CONFIG_DIR"; rm -f "$KUBECONFIG"' EXIT
  az login --tenant 133815cf-acdc-4089-a1e7-fce0de2fe1b4 --use-device-code
  az account set --subscription b4207b90-6a00-470a-aa95-b154c688bb74
  az aks get-credentials -g rg-nk-nonprod -n aks-notekeeper-nonprod --file "$KUBECONFIG"
  kubelogin convert-kubeconfig -l azurecli
  python3 scripts/bootstrap_platform.py --observability "$HOME/dev-observability.json"
  python3 scripts/bootstrap_dev.py --platform "$HOME/dev-platform.json" --values "$HOME/dev-values.json"
  kubectl get pods -A
  kubectl describe nodes
)
exit
```

If the checkout does not exist, first `git clone https://github.com/anuragdchowdhury/ci-cd-project.git`. Bootstrap SQL is idempotent and must report `NOTEKEEPER_DB_READY`. It uses Entra tokens, creates the two SQL identity roles, migrates first, then grants runtime CRUD. The platform script installs checksum-pinned cert-manager/Traefik charts, an internal load balancer, the DNS issuer, and one custom AMA scrape job. It does **not** enable automatic PLS annotations; Terraform owns PLS.

## 4. Deploy and verify private TLS

On the laptop:

```bash
gh workflow run deploy-dev.yml --repo anuragdchowdhury/ci-cd-project \
  --ref main -f release_sha="$RELEASE_SHA"
gh run list --repo anuragdchowdhury/ci-cd-project --workflow deploy-dev.yml --limit 3
```

Require `NOTEKEEPER_DEPLOY_OK FULL_SHA`, not merely ARM Run Command success. This runs Flyway and installs the paired digests through Helm. Backend traces and browser telemetry use separate resources; ingress routes `/api/` to backend and `/` to frontend. The management port remains private. CD deallocates the VM after the attempt.

Start/SSH to the VM again using the temporary **operator** session above. Check:

```bash
kubectl -n notekeeper-dev get ingress,certificate,pods
kubectl -n notekeeper-dev wait --for=condition=Ready certificate/notekeeper-origin-tls --timeout=600s
ORIGIN=$(python3 -c 'import json; print("origin."+json.load(open("../dev-observability.json"))["dev_dns_zone"])')
curl --fail --resolve "$ORIGIN:443:10.20.19.10" "https://$ORIGIN/healthz"
curl --fail --resolve "$ORIGIN:443:10.20.19.10" "https://$ORIGIN/api/notes"
```

Certificate errors: inspect `kubectl -n notekeeper-dev describe certificate,certificaterequest,order,challenge` and cert-manager logs. Check DNS delegation, federation, zone-scoped RBAC propagation and egress. Do not disable certificate verification or create public AKS ingress to bypass failure.

## 5. Provision Front Door Premium and approve its connection

On the laptop, after the actual internal LB exists:

```bash
python3 scripts/configure_edge.py --platform infra/.generated/dev-platform.json \
  --observability infra/.generated/dev-observability.json
terraform -chdir=infra/edge init -backend-config=../.generated/edge.backend.hcl
terraform -chdir=infra/edge plan -var-file=../.generated/edge.auto.tfvars.json -out=edge.tfplan
terraform -chdir=infra/edge show -no-color edge.tfplan
terraform -chdir=infra/edge apply edge.tfplan
terraform -chdir=infra/edge output -json edge > infra/.generated/dev-edge.json
```

This stack adds Premium Front Door, WAF, PLS, origin, routing, custom-domain validation/TLS, Azure DNS alias and selected diagnostics. Both hops use HTTPS with certificate name checks. API caching is absent. WAF blocks requests whose source is outside your configured operator IPv4 `/32`; allowed requests still pass managed rules. Updating your public IP requires regenerating edge inputs and applying a reviewed plan. Requests from the VM's different public IP are blocked, so run public website checks on your laptop.

In **Azure Portal → Private Link services → pls-nk-dev-ingress → Private endpoint connections**, inspect the pending connection. Match it to **afd-nk-dev's private-ingress origin** and its request message `NoteKeeper Dev Front Door Premium to Terraform-managed ingress PLS`. PLS permits discovery from all subscriptions because Front Door uses a Microsoft-managed subscription, but has no auto-approval. Discovery is not connection authorization. Approve that connection only; reject unrelated requests. Then inspect **Front Door → Origin groups → private-aks** and **Domains** until connection approval, domain validation, managed certificate and deployment are ready. Terraform cannot complete your registrar nameserver change or substitute for this connection review.

```bash
curl --fail -I "https://$DEV_ZONE/"
curl --fail -i "https://$DEV_ZONE/api/notes"
```

Open the browser, create/edit/delete a note, refresh, and check persistence. The `azurefd.net` default endpoint is also WAF-restricted. Front Door propagation can take time; distinguish DNS resolution, domain TLS, origin TLS, private-link approval, health probes and application readiness rather than repeatedly rebuilding images.

## 6. Configure Grafana and prove all signal paths

On the laptop with operator Azure login:

```bash
az extension add --name amg --upgrade
python3 scripts/configure_grafana.py --observability infra/.generated/dev-observability.json
python3 scripts/audit_collection.py --platform infra/.generated/dev-platform.json
```

Open the exported Grafana endpoint and sign in with Entra. Grafana's managed identity has Monitoring Data Reader on the metric workspace and Log Analytics Reader on the log workspace. No Grafana API key is enabled. Two versioned dashboards cover RED/JVM/pool/Kubernetes and logs/traces/events. Use the Azure Monitor built-in datasource in Explore for Front Door/PostgreSQL platform metrics.

Verify `up{job="notekeeper-api"}=1`, HTTP counter/histogram, JVM/Hikari and Kubernetes series. The AMA ConfigMap selects only backend management endpoints in Dev; there is no second annotation scrape. Inspect `kubectl -n kube-system get pods` and the AMA target/config diagnostics if a target is absent.

Generate requests and an error drill from [Step 7](07-scenarios.md). In Log Analytics, check ContainerLogV2, KubeEvents, AppRequests and AppDependencies by time and actual trace ID. A sampled response ID alone does not prove ingestion. Open Application Insights Transaction search for the backend/browser components and verify the browser dependency shares the backend W3C operation ID. In the browser Network tab confirm `traceparent` on `/api/notes`; no note content/query string should appear in telemetry.

Normal container collection keeps Dev/scenario ERROR/CRITICAL/FATAL only. Request INFO logs are deliberately dropped. For the correlation training session temporarily enable drill logs:

```bash
python3 scripts/configure_lab.py --dev-zone "$DEV_ZONE" --drill-logs
terraform -chdir=infra/nonprod plan \
  -var-file=../.generated/nonprod.auto.tfvars.json \
  -var-file=../.generated/access.auto.tfvars.json \
  -var-file=../.generated/lab.auto.tfvars.json -out=drill-logs.tfplan
terraform -chdir=infra/nonprod show -no-color drill-logs.tfplan
terraform -chdir=infra/nonprod apply drill-logs.tfplan
```

Require only the intended DCR transform change. After drills, run configure_lab **without** `--drill-logs` and repeat saved-plan review/apply to restore filtering. Drill traffic temporarily uses 100% trace sampling and restores 10%; managed log/trace delivery and alert evaluation can lag several minutes.

## Signal ownership, retention and security exception

| Signal | Single intended owner | Retention / volume |
|---|---|---|
| Kubernetes + JVM/HTTP/Hikari metrics | AKS Managed Prometheus + one custom service scrape → Monitor Workspace | Azure-managed 18-month retention; cannot set this to 30 days |
| Container stdout/stderr | AMA → explicit ContainerLogV2 DCR flow | 30-day LAW; error-only normally, Dev/scenario namespaces |
| Kubernetes events | AMA → KubeEvents DCR flow | 30 days; separate from application severity filtering |
| Backend requests/dependencies | Existing Java OpenTelemetry-based AI agent → backend AI/LAW | 30 days, routine 10% sampling; agent log/Micrometer export disabled |
| Browser requests/page views/dependencies | Browser SDK → separate browser AI/LAW | 30 days; public ingestion, sanitized URLs, no cookies/note content |
| Front Door/WAF, vault, DB, scheduler/controller diagnostics | One selected diagnostic setting per resource → LAW | 30 days; no AllMetrics copy or overlapping allLogs group |
| Optional archive | One ContainerLogV2 LAW export → dedicated Storage | Delete after seven days since modification; one-day soft delete; asynchronous lifecycle |

**Explicit lab exception:** pinned Java agent 3.7.9 supports IMDS managed-identity ingestion, not direct projected workload-token authentication. This bundle uses connection-string ingestion for backend/browser AI rather than inventing an unsupported workload-identity configuration. These strings identify an ingestion resource, do not grant telemetry reading, and the browser string is necessarily public. Local ingestion authentication remains enabled; telemetry spoofing/volume is possible. PostgreSQL, Key Vault, cert-manager DNS, ACR pulls and deployment retain their passwordless identities. A production redesign would validate a supported authenticated collector/agent path and private telemetry networking before disabling local ingestion. Metrics/log collectors follow the supported AKS managed identity onboarding path; they do not use application database credentials.

LAW's 0.5-GB daily quota is a delayed soft safeguard, not a hard spending/ingestion cap; it can interrupt evidence collection. Budget emails also do not stop spending. Avoid raw user data in logs and do not enable database statement logging. The browser/frontend and backend are intentionally distinct telemetry resources, not duplicate exporters of the same signal.

`audit_collection.py` requires exactly the two Terraform-owned DCR associations. If Azure onboarding left another association, inspect its destination/streams and ownership before removing/importing anything. Also review diagnostic settings and AMA targets. A matching repeated message can be a retry or genuine repeated request: compare source timestamp/container/message, DCR paths and operation IDs. Distributed collection offers no universal exactly-once guarantee.

## 7. Optional storage retention exercise

Run baseline/error first so ContainerLogV2, AppRequests and AppDependencies exist; Terraform's LAW table resource updates existing tables. Confirm these tables exist in Portal → workspace → Tables. Then:

```bash
python3 scripts/configure_lab.py --dev-zone "$DEV_ZONE" --archive
terraform -chdir=infra/nonprod plan \
  -var-file=../.generated/nonprod.auto.tfvars.json \
  -var-file=../.generated/access.auto.tfvars.json \
  -var-file=../.generated/lab.auto.tfvars.json -out=archive.tfplan
terraform -chdir=infra/nonprod show -no-color archive.tfplan
terraform -chdir=infra/nonprod apply archive.tfplan
```

Generate fresh errors; LAW export does not backfill existing rows. Inspect the new log storage account's `am-containerlogv2` container using Entra login. Storage has no account-key auth or public blobs, permits the operator IP/trusted Azure service path, and operator receives Blob Data Reader. Verify export status and lifecycle configuration. This is **one intentional second-store archive copy**, not a second LAW ingestion path; neither export delivery nor lifecycle timing is guaranteed exactly once/immediate. Active blobs are eligible seven days after modification, recoverable soft deletion adds a day, and lifecycle processing is asynchronous. No AppInsights diagnostic export duplicates are configured.

## Costs, pause and cleanup

The recorded quota is now fully allocated: eight AKS vCPUs plus two VM vCPUs. No zero-surge system-pool upgrade is supported by this pinned provider/AKS combination. Do not add nodes or assume automatic upgrades fit quota. Charts/agents consume existing CPU/memory; inspect node requests before drills.

Premium Front Door and Standard Grafana have recurring charges even with no requests. Check Cost Management immediately after provisioning against the remaining credits; the ₹3,000 budget is notification only. VM deallocation saves its compute, not disks/IP, database, Front Door, Grafana, logs or endpoints. Pausing the VM is not pausing the lab bill.

For final cleanup, preserve exported evidence and notes you want to retain. Review a saved **edge destroy plan** first; apply it before deleting the ingress load balancer, because PLS references its frontend:

```bash
terraform -chdir=infra/edge plan -destroy \
  -var-file=../.generated/edge.auto.tfvars.json -out=edge-destroy.tfplan
terraform -chdir=infra/edge show -no-color edge-destroy.tfplan
terraform -chdir=infra/edge apply edge-destroy.tfplan
```

Then, from private operator access, uninstall the app/controllers and remove the custom AMA ConfigMap. Review a nonprod saved destroy plan with **all three variable files** if ending the entire lab, or explicitly change only lab flags if retaining the foundation. Destruction of the platform removes its database: confirm backups/retained data first. Private-link dependencies and provider deletion ordering may require retrying a reviewed plan after removals; never discard state. Before destroying the Azure DNS zone, move any retained DNS records to another DNS host and update Namecheap nameservers; do not leave the domain delegated to a deleted zone. Bootstrap, ACR and remote-state storage are separate roots and must remain intact unless separately reviewed for final account cleanup.

## Completion evidence

Save the reviewed/apply summaries, final nonprod/edge **No changes**, SQL/CD success markers, trusted TLS checks, both deployed digests, Grafana panels, actual trace/log operation IDs, alert Fired/Resolved and email timestamps, and drill cleanup. Code/CI validation is not evidence that Azure provisioning or a scenario has already succeeded.

References: [private Front Door origin](https://learn.microsoft.com/azure/frontdoor/standard-premium/how-to-enable-private-link-internal-load-balancer), [Container Insights transformations](https://learn.microsoft.com/azure/azure-monitor/containers/container-insights-transformations), [managed Prometheus overview](https://learn.microsoft.com/azure/azure-monitor/metrics/prometheus-metrics-overview), [Java agent configuration](https://learn.microsoft.com/azure/azure-monitor/app/java-standalone-config), [LAW export](https://learn.microsoft.com/azure/azure-monitor/logs/logs-data-export).
